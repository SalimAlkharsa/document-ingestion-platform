import pdb
import os
import redis
import json
import time
import logging
import tempfile
import argparse
import sys
import signal
import threading
from pathlib import Path
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter, InputFormat
from docling.datamodel.document import DoclingDocument
from dotenv import load_dotenv
from transformers import AutoTokenizer

# Add the parent directory to sys.path to import globals
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from globals import MAX_TOKENS, REDIS_QUEUE, EMBEDDING_QUEUE, PROCESSED_DIR, CHUNKING_DLQ

# Load environment variables
load_dotenv()

# Initialize the Hugging Face tokenizer and Redis client
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Shutdown event for graceful termination
shutdown_event = threading.Event()
worker_id = None  # Will be set from CLI args


def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"worker_id={worker_id} stage=chunking event=shutdown_requested")
    shutdown_event.set()


# Register signal handlers
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

def chunk_document(document, file_path, trace_id, metadata=None):
    """
    Chunk the document using the HybridChunker.
    Takes a Docling Document object directly - no re-conversion needed.
    """
    logger.info(
        f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
        f"event=chunking_started file={os.path.basename(file_path)}"
    )
    
    chunker = HybridChunker(
        tokenizer=tokenizer,
        max_tokens=MAX_TOKENS,
        merge_peers=True,
    )
    
    logger.debug(
        f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
        f"event=chunker_initialized max_tokens={MAX_TOKENS}"
    )
    
    # Chunk the document directly - no temp file needed!
    chunk_iter = chunker.chunk(dl_doc=document)
    chunks = [chunker.serialize(chunk) for chunk in chunk_iter]
    
    logger.info(
        f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
        f"event=chunking_completed file={os.path.basename(file_path)} "
        f"chunk_count={len(chunks)}"
    )

    # Use the metadata passed from extraction if available
    if metadata:
        processed_metadata = metadata.copy()
        # Add chunking-specific metadata
        processed_metadata = metadata.copy()
        processed_metadata.update({
            "chunks_count": len(chunks),
            "chunking_timestamp": time.time(),
            "chunking_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    else:
        # Fallback metadata
        processed_metadata = {
            "file_path": file_path,
            "chunks_count": len(chunks),
            "chunking_timestamp": time.time(),
            "chunking_time": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    return chunks, processed_metadata

def save_chunks(file_path, chunks, metadata, trace_id):
    """
    Save the chunks to the processed folder.
    """
    # Create processed directory if it doesn't exist
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
    
    logger.debug(
        f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
        f"event=chunks_saved file={output_file}"
    )
    
    return output_file

def add_to_embedding_queue(chunks_file, metadata, trace_id):
    """
    Add the chunked file to the embedding queue.
    """
    queue_item = {
        "chunks_file": chunks_file,
        "metadata": metadata
    }
    redis_client.rpush(EMBEDDING_QUEUE, json.dumps(queue_item))
    
    logger.info(
        f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
        f"event=queued_for_embedding queue={EMBEDDING_QUEUE} file={chunks_file}"
    )

def process_chunking_job(job_data):
    """
    Process a chunking job from the chunking queue.
    Deserializes Document object and chunks it without re-conversion.
    """
    trace_id = job_data.get('trace_id', 'unknown')
    file_path = job_data['file_path']
    filename = job_data.get('filename', os.path.basename(file_path))
    
    logger.info(
        f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
        f"event=job_started file={filename}"
    )
    
    try:
        # Get the serialized document
        document_json = job_data.get('document_json')
        metadata = job_data.get('metadata', {})
        
        if not document_json:
            # Fallback to markdown if document_json not available (backward compatibility)
            logger.warning(
                f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
                f"event=no_document_json file={filename} using_markdown_fallback=true"
            )
            markdown_output = job_data.get('markdown_output', '')
            
            # Old method: convert markdown to document (what we're trying to avoid)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as temp_md_file:
                temp_md_file.write(markdown_output.encode('utf-8'))
                temp_md_file_path = temp_md_file.name
            
            converter = DocumentConverter(allowed_formats=["md"])
            result = converter.convert(temp_md_file_path)
            document = result.document
            os.remove(temp_md_file_path)
        else:
            # New method: deserialize Document directly from JSON
            logger.debug(
                f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
                f"event=deserializing_document file={filename}"
            )
            document = DoclingDocument.model_validate(document_json)
        
        # Chunk the document
        chunks, processed_metadata = chunk_document(document, file_path, trace_id, metadata)
        
        # Save chunks to file
        chunks_file = save_chunks(file_path, chunks, processed_metadata, trace_id)
        
        # Add to embedding queue
        add_to_embedding_queue(chunks_file, processed_metadata, trace_id)
        
        logger.info(
            f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
            f"event=job_completed file={filename} status=success"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            f"trace_id={trace_id} worker_id={worker_id} stage=chunking "
            f"event=job_failed file={filename} error={str(e)}"
        )
        logger.exception("Detailed error information:")
        
        # Could push to DLQ here for retry logic
        # redis_client.rpush(CHUNKING_DLQ, json.dumps({**job_data, 'error': str(e)}))
        
        return False

def process_chunking_queue():
    """
    Main worker loop - process chunking jobs from the queue using atomic BLPOP.
    """
    logger.info(
        f"worker_id={worker_id} stage=chunking event=worker_started "
        f"queue={REDIS_QUEUE}"
    )
    
    while not shutdown_event.is_set():
        try:
            # Atomic blocking pop from chunking queue (5 second timeout)
            result = redis_client.brpop(REDIS_QUEUE, timeout=5)
            
            if result:
                _, job_item = result
                job_data = json.loads(job_item)
                
                # Process the chunking job
                process_chunking_job(job_data)
            else:
                # No item in queue, continue waiting
                logger.debug(
                    f"worker_id={worker_id} stage=chunking event=queue_empty "
                    f"queue={REDIS_QUEUE}"
                )
                
        except Exception as e:
            logger.error(
                f"worker_id={worker_id} stage=chunking event=worker_error "
                f"error={str(e)}"
            )
            logger.exception("Detailed error information:")
            time.sleep(5)  # Back off on error
    
    logger.info(
        f"worker_id={worker_id} stage=chunking event=shutdown_complete"
    )

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Document chunking worker")
    parser.add_argument("--worker-id", type=str, required=True, help="Unique worker identifier")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    # Set worker ID
    worker_id = args.worker_id
    
    # Configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"worker_id={worker_id} stage=chunking event=starting")
        process_chunking_queue()
    except KeyboardInterrupt:
        logger.info(f"worker_id={worker_id} stage=chunking event=keyboard_interrupt")
    finally:
        logger.info(f"worker_id={worker_id} stage=chunking event=stopped")


