import pdb
import os
import redis
import json
import time
import logging
import tempfile
import argparse
import sys
from pathlib import Path
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from dotenv import load_dotenv
from transformers import AutoTokenizer

# Add the parent directory to sys.path to import globals
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from globals import MAX_TOKENS, REDIS_QUEUE, EMBEDDING_QUEUE, PROCESSED_DIR

# Load environment variables
load_dotenv()

# Initialize the Hugging Face tokenizer and Redis client
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

def chunk_file(file_path, markdown_output, json_output, metadata=None):
    """
    Chunk the document using the HybridChunker.
    """
    logger.info(f"Chunking file: {file_path}")
    
    logger.info(f"MD has type {type(markdown_output)}")
    
    chunker = HybridChunker(
        tokenizer=tokenizer,
        max_tokens=MAX_TOKENS,
        merge_peers=True,
    )

    # Write the markdown_output to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as temp_md_file:
        temp_md_file.write(markdown_output.encode('utf-8'))
        temp_md_file_path = temp_md_file.name

    # Now turn the md into a docling document
    converter = DocumentConverter(allowed_formats=["md"])
    result = converter.convert(temp_md_file_path)
    document = result.document

    # Remove the temporary file
    os.remove(temp_md_file_path)
    
    logger.info("Starting chunking...")
    chunk_iter = chunker.chunk(dl_doc=document)
    chunks = [chunker.serialize(chunk) for chunk in chunk_iter]
    
    logger.debug(f"Chunks: {chunks}")

    # Use the metadata passed from extraction if available
    if metadata:
        processed_metadata = metadata.copy()
        # Add chunking-specific metadata
        processed_metadata.update({
            "chunks_count": len(chunks),
            "chunking_timestamp": time.time(),
            "chunking_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    else:
        # Fallback to extracting basic metadata (legacy approach)
        processed_metadata = {
            "file_path": file_path,
            "original_json": json_output,
            "timestamp": time.time()
        }
    
    return chunks, processed_metadata

def save_chunks(file_path, chunks, metadata):
    """
    Save the chunks to the debug folder for review.
    """
    # Create debug directory if it doesn't exist
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    # Generate a filename based on the original filename
    base_filename = os.path.basename(file_path)
    output_file = os.path.join(PROCESSED_DIR, f"{base_filename}_chunks.json")
    
    # Save chunks along with metadata
    output_data = {
        "chunks": chunks,
        "metadata": metadata
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=4)
    logger.info(f"Chunks saved to {output_file}")
    
    return output_file

def add_to_embedding_queue(chunks_file, metadata):
    """
    Add the chunked file to the embedding queue.
    """
    queue_item = {
        "chunks_file": chunks_file,
        "metadata": metadata
    }
    redis_client.rpush(EMBEDDING_QUEUE, json.dumps(queue_item))
    logger.info(f"Added {chunks_file} to embedding queue")

def process_queue():
    """
    Process documents from the Redis queue.
    """
    while True:
        # TODO: Make this in a way that can be parallelized
        item = redis_client.lindex(REDIS_QUEUE, 0)
        if item:
            data = json.loads(item)
            file_path = data['file_path']
            markdown_output = data['markdown_output']
            json_output = data['json_output']
            
            # Extract metadata if available from the extraction process
            metadata = data.get('metadata', None)
            
            logger.info(f"Processing document with metadata: {metadata and 'Available' or 'Not available'}")
            
            chunks, processed_metadata = chunk_file(file_path, markdown_output, json_output, metadata)
            chunks_file = save_chunks(file_path, chunks, processed_metadata)
            
            # Add to embedding queue
            add_to_embedding_queue(chunks_file, processed_metadata)
            
            logger.info(f"Processed chunks for file: {file_path}")
            item = redis_client.lpop(REDIS_QUEUE)
        else:
            time.sleep(5)  # Wait for 5 seconds before checking the queue again
            # TODO: Create a stop condition for the loop via cooldown period or external signal

if __name__ == "__main__":
    # Parse command-line arguments to determine the mode of operation and debug flag
    parser = argparse.ArgumentParser(description="Document chunking script")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Process the queue
    process_queue()

