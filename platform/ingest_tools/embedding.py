import pdb
import os
import redis
import json
import time
import logging
import argparse
import sys
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from datetime import datetime

# Add the parent directory to sys.path to import globals
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from globals import EMBEDDING_QUEUE, PROCESSED_DIR

# Import MongoDBHelper from the db module (relative to platform directory)
sys.path.insert(0, str(project_root / 'platform'))
from db.mongodb_helper import MongoDBHelper

# Load environment variables
load_dotenv()

# Initialize Redis client
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# Define the simulated vector store directory (keeping for backward compatibility)
SIMULATED_VECTOR_STORE = os.path.join(PROCESSED_DIR, 'simulated_vector_store')

# Initialize MongoDB helper
mongo_helper = None

def get_mongo_helper():
    """
    Get or initialize the MongoDB helper singleton
    """
    global mongo_helper
    if mongo_helper is None:
        mongo_helper = MongoDBHelper()
    return mongo_helper

class Embedder:
    def __init__(self, model_name="all-mpnet-base-v2"):
        """
        Initialize the embedder with a sentence transformer model.
        """
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        logger.info(f"Initialized embedder with model: {model_name}")
    
    def embed_chunks(self, chunks, metadata=None):
        """
        Embed a list of text chunks and enrich with metadata fields.
        """
        logger.debug(f"Embedding {len(chunks)} chunks with metadata")
        
        # Extract texts from chunks based on their structure
        texts = []
        for chunk in chunks:
            if isinstance(chunk, dict) and 'text' in chunk:
                texts.append(chunk['text'])
            else:
                texts.append(str(chunk))
        
        # Generate embeddings
        embeddings = self.model.encode(texts)
        
        # Prepare enriched chunks with embeddings and metadata
        enriched_chunks = []
        for i, chunk in enumerate(chunks):
            # Start with original chunk if it's a dictionary, otherwise create one
            if isinstance(chunk, dict):
                enriched_chunk = chunk.copy()
            else:
                enriched_chunk = {"text": str(chunk)}
            
            # Add embedding
            enriched_chunk["embedding"] = embeddings[i].tolist()
            
            # Add embedding metadata
            enriched_chunk["embedding_model"] = self.model_name
            enriched_chunk["embedding_timestamp"] = time.time()
            enriched_chunk["embedding_date"] = datetime.now().isoformat()
            
            # Add common metadata fields to each chunk if provided
            if metadata:
                # Add selected metadata fields directly to each chunk
                important_fields = [
                    "file_path", "title", "author", "date", "source", "url",
                    "doc_type", "category", "tags", "language"
                ]
                
                for field in important_fields:
                    if field in metadata:
                        enriched_chunk[field] = metadata[field]
                
                # Add a document_id if available
                if "document_id" in metadata:
                    enriched_chunk["document_id"] = metadata["document_id"]
                elif "file_path" in metadata:
                    # Create a simple hash as document_id if not provided
                    doc_path = metadata["file_path"]
                    enriched_chunk["document_id"] = f"doc_{hash(doc_path) % 10000000:07d}"
            
            enriched_chunks.append(enriched_chunk)
        
        return enriched_chunks

def load_chunks_file(chunks_file):
    """
    Load chunks and metadata from a JSON file.
    """
    try:
        with open(chunks_file, 'r') as f:
            data = json.load(f)
        
        logger.debug(f"Loaded data keys from file: {list(data.keys())}")
        
        if 'chunks' in data:
            chunks = data['chunks']
        else:
            logger.warning(f"No 'chunks' key found in {chunks_file}, trying alternative keys")
            # Fallback to other possible keys
            for key in ["documents", "items", "texts"]:
                if key in data:
                    chunks = data[key]
                    break
            else:
                # If no chunks found, raise exception
                raise KeyError(f"No chunks found in {chunks_file}")
        
        metadata = data.get('metadata', {})
        
        # Add file path to metadata if not present
        if 'file_path' not in metadata and isinstance(chunks_file, str):
            metadata['file_path'] = chunks_file
        
        return chunks, metadata
    
    except Exception as e:
        logger.error(f"Error loading chunks file {chunks_file}: {str(e)}")
        raise

def save_to_mongodb(embedded_chunks, metadata):
    """
    Save each embedded chunk as a separate document in MongoDB.
    """
    # Get MongoDB helper
    mongo_db = get_mongo_helper()
    
    # Generate a unique filename based on metadata
    file_path = metadata.get('file_path', 'unknown')
    
    # Create a document ID for consistent reference
    if "document_id" not in metadata:
        doc_id = f"doc_{hash(file_path) % 10000000:07d}"
        metadata["document_id"] = doc_id
    else:
        doc_id = metadata["document_id"]
    
    # Store each embedded chunk as its own document in MongoDB
    result_ids = []
    for i, chunk in enumerate(embedded_chunks):
        # Add metadata and chunk-specific information to each chunk document
        chunk_metadata = {**metadata, "chunk_index": i, "document_id": doc_id}
        
        # Prepare the document with the chunk's data and metadata
        chunk_document = {
            "text": chunk.get("text", ""),
            "embedding": chunk.get("embedding", []),
            "embedding_model": chunk.get("embedding_model", metadata.get("embedding_model", "all-MiniLM-L6-v2")),
            "embedding_timestamp": chunk.get("embedding_timestamp", time.time()),
            "embedding_date": chunk.get("embedding_date", datetime.now().isoformat()),
            "metadata": chunk_metadata
        }

        # Store the chunk document in MongoDB
        result_id = mongo_db.store_embeddings(
            document_id=f"{doc_id}_{i}",  # Unique ID for each chunk
            metadata=chunk_metadata,
            embedded_chunks=[chunk_document],  # Each chunk is stored as its own document
            vector_info={
                "count": 1,  # One chunk per document
                "dimensions": len(chunk["embedding"]) if chunk["embedding"] else 0,
                "model": chunk.get("embedding_model", "all-MiniLM-L6-v2")
            }
        )
        
        result_ids.append(result_id)

    logger.info(f"Embeddings saved to MongoDB with document_id: {doc_id}, {len(embedded_chunks)} chunks")
    
    return result_ids

def save_to_vector_store(embedded_chunks, metadata):
    """
    Save the embedded chunks to the simulated vector store in an improved format.
    Legacy function maintained for backward compatibility and also debugging usefulness
    """
    # Create the simulated vector store directory if it doesn't exist
    os.makedirs(SIMULATED_VECTOR_STORE, exist_ok=True)
    
    # Generate a unique filename based on metadata
    file_path = metadata.get('file_path', 'unknown')
    base_filename = os.path.basename(file_path)
    timestamp = metadata.get('chunking_timestamp', time.time())
    
    # Create a document ID for consistent reference
    if "document_id" not in metadata:
        doc_id = f"doc_{hash(file_path) % 10000000:07d}"
        metadata["document_id"] = doc_id
    else:
        doc_id = metadata["document_id"]
    
    # Prepare output data with improved structure for simulated vector store
    output_data = {
        "document_id": doc_id,
        "metadata": metadata,
        "vectors": {
            "count": len(embedded_chunks),
            "dimensions": len(embedded_chunks[0]["embedding"]) if embedded_chunks else 0,
            "model": metadata.get("embedding_model", "all-MiniLM-L6-v2")
        },
        "embedded_chunks": embedded_chunks,
        "processing": {
            "embedding_timestamp": time.time(),
            "embedding_time": datetime.now().isoformat()
        }
    }
    
    # Use document_id in filename for better traceability
    output_file = os.path.join(SIMULATED_VECTOR_STORE, f"{doc_id}_{base_filename}_embeddings.json")
    
    # Save to file
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=4)
    
    logger.info(f"Embeddings saved to {output_file} with {len(embedded_chunks)} chunks")
    
    # Also create a lightweight index file for quick lookup
    index_file = os.path.join(SIMULATED_VECTOR_STORE, "vector_store_index.jsonl")
    index_entry = {
        "document_id": doc_id,
        "file_path": file_path,
        "embedding_file": output_file,
        "chunks_count": len(embedded_chunks),
        "timestamp": time.time(),
        "title": metadata.get("title", base_filename)
    }
    
    # Append to index file
    with open(index_file, 'a') as f:
        f.write(json.dumps(index_entry) + "\n")
    
    return output_file

def process_queue():
    """
    Process documents from the embedding queue.
    """
    embedder = Embedder()
    
    while True:
        # Get the next item from the queue
        item = redis_client.lindex(EMBEDDING_QUEUE, 0)
        if item:
            try:
                data = json.loads(item)
                chunks_file = data['chunks_file']
                metadata = data['metadata']
                
                logger.info(f"Processing embeddings for: {chunks_file}")
                
                # Load chunks
                chunks, file_metadata = load_chunks_file(chunks_file)
                
                # Combine metadata if needed
                if metadata and file_metadata:
                    combined_metadata = {**file_metadata, **metadata}
                else:
                    combined_metadata = metadata or file_metadata or {}
                
                # Add embedding model information to metadata
                combined_metadata["embedding_model"] = embedder.model_name
                
                # Embed chunks with enhanced metadata integration
                embedded_chunks = embedder.embed_chunks(chunks, combined_metadata)
                
                # Save to MongoDB (primary storage)
                document_id = save_to_mongodb(embedded_chunks, combined_metadata)
                
                # For backward compatibility, also save to file system if needed
                # Uncomment if you want to maintain file-based storage alongside MongoDB
                # output_file = save_to_vector_store(embedded_chunks, combined_metadata)
                
                logger.info(f"Successfully embedded chunks from {chunks_file} with document_id {document_id}")
                
                # Remove the processed item from the queue
                redis_client.lpop(EMBEDDING_QUEUE)
                
            except Exception as e:
                logger.error(f"Error processing embeddings: {str(e)}")
                logger.exception("Detailed error information:")
                # Consider implementing a dead letter queue or retry mechanism
                # Uncomment the following line to remove failing items from the queue
                # redis_client.lpop(EMBEDDING_QUEUE)
        else:
            logger.debug("No items in embedding queue, waiting...")
            time.sleep(5)  # Wait before checking again

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Document embedding script")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Create required directories
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(SIMULATED_VECTOR_STORE, exist_ok=True)
    
    logger.info("Starting embedding process...")
    process_queue()
