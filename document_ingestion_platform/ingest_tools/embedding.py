import pdb
import os
import redis
import json
import time
import logging
import argparse
import sys
import signal
import threading
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from datetime import datetime

# Add the parent directory to sys.path to import globals
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from globals import EMBEDDING_QUEUE, PROCESSED_DIR, EMBEDDING_DLQ

# Import MongoDBHelper from the db module (relative to platform directory)
sys.path.insert(0, str(project_root / 'platform'))
from document_ingestion_platform.db.mongodb_helper import MongoDBHelper

# Load environment variables
load_dotenv()

# Initialize Redis client
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Define the simulated vector store directory (keeping for backward compatibility)
SIMULATED_VECTOR_STORE = os.path.join(PROCESSED_DIR, 'simulated_vector_store')

# Initialize MongoDB helper
mongo_helper = None

# Shutdown event for graceful termination
shutdown_event = threading.Event()
worker_id = None  # Will be set from CLI args


def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"worker_id={worker_id} stage=embedding event=shutdown_requested")
    shutdown_event.set()


# Register signal handlers
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

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
        logger.info(
            f"worker_id={worker_id} stage=embedding event=embedder_initialized "
            f"model={model_name}"
        )
    
    def embed_chunks(self, chunks, metadata=None, trace_id=None):
        """
        Embed a list of text chunks and enrich with metadata fields.
        """
        logger.debug(
            f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
            f"event=embedding_started chunk_count={len(chunks)}"
        )
        
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
        
        logger.debug(
            f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
            f"event=embedding_completed chunk_count={len(enriched_chunks)}"
        )
        
        return enriched_chunks

def load_chunks_file(chunks_file, trace_id=None):
    """
    Load chunks and metadata from a JSON file.
    """
    try:
        with open(chunks_file, 'r') as f:
            data = json.load(f)
        
        logger.debug(
            f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
            f"event=chunks_loaded file={chunks_file} keys={list(data.keys())}"
        )
        
        if 'chunks' in data:
            chunks = data['chunks']
        else:
            logger.warning(
                f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
                f"event=no_chunks_key file={chunks_file}"
            )
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
        logger.error(
            f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
            f"event=load_error file={chunks_file} error={str(e)}"
        )
        raise

def save_to_mongodb(embedded_chunks, metadata, trace_id=None):
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
    
    logger.debug(
        f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
        f"event=mongodb_save_started document_id={doc_id} chunk_count={len(embedded_chunks)}"
    )
    
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

    logger.info(
        f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
        f"event=mongodb_save_completed document_id={doc_id} chunk_count={len(embedded_chunks)}"
    )
    
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

def process_embedding_job(embedder, job_data):
    """
    Process an embedding job from the embedding queue.
    """
    trace_id = job_data.get('metadata', {}).get('trace_id', 'unknown')
    chunks_file = job_data['chunks_file']
    metadata = job_data['metadata']
    
    logger.info(
        f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
        f"event=job_started file={chunks_file}"
    )
    
    try:
        # Load chunks
        chunks, file_metadata = load_chunks_file(chunks_file, trace_id)
        
        # Combine metadata if needed
        if metadata and file_metadata:
            combined_metadata = {**file_metadata, **metadata}
        else:
            combined_metadata = metadata or file_metadata or {}
        
        # Add embedding model information to metadata
        combined_metadata["embedding_model"] = embedder.model_name
        
        # Embed chunks with enhanced metadata integration
        embedded_chunks = embedder.embed_chunks(chunks, combined_metadata, trace_id)
        
        # Save to MongoDB (primary storage)
        document_ids = save_to_mongodb(embedded_chunks, combined_metadata, trace_id)
        
        # For backward compatibility, also save to file system if needed
        # Uncomment if you want to maintain file-based storage alongside MongoDB
        # output_file = save_to_vector_store(embedded_chunks, combined_metadata)
        
        logger.info(
            f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
            f"event=job_completed file={chunks_file} status=success "
            f"chunk_count={len(embedded_chunks)}"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            f"trace_id={trace_id} worker_id={worker_id} stage=embedding "
            f"event=job_failed file={chunks_file} error={str(e)}"
        )
        logger.exception("Detailed error information:")
        
        # Could push to DLQ here for retry logic
        # redis_client.rpush(EMBEDDING_DLQ, json.dumps({**job_data, 'error': str(e)}))
        
        return False

def process_embedding_queue():
    """
    Main worker loop - process embedding jobs from the queue using atomic BLPOP.
    """
    embedder = Embedder()
    
    logger.info(
        f"worker_id={worker_id} stage=embedding event=worker_started "
        f"queue={EMBEDDING_QUEUE}"
    )
    
    while not shutdown_event.is_set():
        try:
            # Atomic blocking pop from embedding queue (5 second timeout)
            result = redis_client.brpop(EMBEDDING_QUEUE, timeout=5)
            
            if result:
                _, job_item = result
                job_data = json.loads(job_item)
                
                # Process the embedding job
                process_embedding_job(embedder, job_data)
            else:
                # No item in queue, continue waiting
                logger.debug(
                    f"worker_id={worker_id} stage=embedding event=queue_empty "
                    f"queue={EMBEDDING_QUEUE}"
                )
                
        except Exception as e:
            logger.error(
                f"worker_id={worker_id} stage=embedding event=worker_error "
                f"error={str(e)}"
            )
            logger.exception("Detailed error information:")
            time.sleep(5)  # Back off on error
    
    logger.info(
        f"worker_id={worker_id} stage=embedding event=shutdown_complete"
    )

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Document embedding worker")
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
    
    # Create required directories
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(SIMULATED_VECTOR_STORE, exist_ok=True)
    
    try:
        logger.info(f"worker_id={worker_id} stage=embedding event=starting")
        process_embedding_queue()
    except KeyboardInterrupt:
        logger.info(f"worker_id={worker_id} stage=embedding event=keyboard_interrupt")
    finally:
        logger.info(f"worker_id={worker_id} stage=embedding event=stopped")
