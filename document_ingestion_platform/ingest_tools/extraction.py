import argparse
import os
import logging
from pathlib import Path
import shutil
import sys
import redis
import json
import datetime
import signal
import threading
import time
from docling.document_converter import DocumentConverter

# Add the parent directory to sys.path to import globals
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from globals import MASTER_LIBRARY, PROCESSED_DIR, REDIS_QUEUE, EXTRACTION_JOBS, EXTRACTION_DLQ

# Import DocumentDBHandler from the db module (relative to platform directory)
sys.path.insert(0, str(project_root / 'platform'))
from document_ingestion_platform.db.db_handler import DocumentDBHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize the document converter and Redis client
converter = DocumentConverter()
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)
db_handler = DocumentDBHandler()

# Shutdown event for graceful termination
shutdown_event = threading.Event()
worker_id = None  # Will be set from CLI args


def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"worker_id={worker_id} stage=extraction event=shutdown_requested")
    shutdown_event.set()


# Register signal handlers
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

def is_processed(file_path):
    """
    Check if a file has already been processed.
    """
    status = db_handler.get_document_status(file_path)
    return status == "processed" or status == "error"

def mark_as_processed(file_path, status="processed", error_message=None):
    """
    Mark the file as processed in the database without moving it from the master library.
    """
    db_handler.update_document_status(file_path, status, error_message)
    # We no longer move the file to preserve it in the master library
    # if status == "processed":
    #     shutil.move(file_path, os.path.join(PROCESSED_DIR, os.path.basename(file_path)))

def extract_metadata(document, file_path, trace_id=None):
    """
    Extract relevant metadata from the document.
    """
    metadata = {
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "file_type": os.path.splitext(file_path)[1][1:],
        "extraction_date": datetime.datetime.now().isoformat(),
        "file_size": os.path.getsize(file_path)
    }
    
    # Add trace_id if provided
    if trace_id:
        metadata["trace_id"] = trace_id
    
    # Extract metadata from document if available
    if hasattr(document, 'metadata') and document.metadata:
        doc_meta = document.metadata
        # Commonly available metadata fields
        for key in ['title', 'author', 'subject', 'keywords', 'creator', 'producer',
                   'creation_date', 'modified_date', 'language']:
            if key in doc_meta:
                metadata[key] = doc_meta[key]
    
    # If title not found, use filename without extension as fallback
    if 'title' not in metadata or not metadata['title']:
        metadata['title'] = os.path.splitext(os.path.basename(file_path))[0]
    
    logger.debug(f"trace_id={trace_id} worker_id={worker_id} stage=extraction event=metadata_extracted")
    return metadata

def process_extraction_job(job_data):
    """
    Process an extraction job from the extraction queue.
    Converts PDF to Docling Document and serializes for chunking.
    """
    trace_id = job_data.get('trace_id', 'unknown')
    file_path = job_data['file_path']
    filename = job_data['filename']
    
    logger.info(
        f"trace_id={trace_id} worker_id={worker_id} stage=extraction "
        f"event=job_started file={filename}"
    )
    
    try:
        # Update status to 'processing'
        db_handler.update_document_status(file_path, "processing")
        
        logger.debug(
            f"trace_id={trace_id} worker_id={worker_id} stage=extraction "
            f"event=conversion_started file={filename}"
        )
        
        # Convert PDF to Docling Document
        result = converter.convert(file_path)
        document = result.document
        
        if not document:
            error_msg = "Failed to convert document - no document returned"
            logger.error(
                f"trace_id={trace_id} worker_id={worker_id} stage=extraction "
                f"event=conversion_failed file={filename} error={error_msg}"
            )
            db_handler.update_document_status(file_path, "error", error_msg)
            return False
        
        logger.debug(
            f"trace_id={trace_id} worker_id={worker_id} stage=extraction "
            f"event=conversion_completed file={filename}"
        )
        
        # Extract metadata from the document
        metadata = extract_metadata(document, file_path, trace_id)
        
        # Serialize the Document object as JSON for chunking
        # This avoids the need to re-convert from markdown
        doc_json = document.export_to_dict()
        markdown_output = document.export_to_markdown()
        
        # Prepare payload for chunking queue
        payload = {
            'trace_id': trace_id,
            'file_path': file_path,
            'filename': filename,
            'document_json': doc_json,  # Serialized Document for chunking
            'markdown_output': markdown_output,  # Keep for backward compatibility
            'metadata': metadata,
            'format': 'json',
            'extraction_timestamp': time.time(),
            'worker_id': worker_id
        }
        
        # Push to chunking queue
        redis_client.rpush(REDIS_QUEUE, json.dumps(payload))
        
        logger.info(
            f"trace_id={trace_id} worker_id={worker_id} stage=extraction "
            f"event=job_completed file={filename} status=success queue={REDIS_QUEUE}"
        )
        
        # Mark as processed in DB
        db_handler.update_document_status(file_path, "processed")
        
        # Release the lock
        lock_key = f"lock:extraction:{filename}"
        redis_client.delete(lock_key)
        
        return True
        
    except Exception as e:
        error_msg = f"Exception during processing: {str(e)}"
        logger.error(
            f"trace_id={trace_id} worker_id={worker_id} stage=extraction "
            f"event=job_failed file={filename} error={error_msg}"
        )
        logger.exception("Detailed error information:")
        
        db_handler.update_document_status(file_path, "error", error_msg)
        
        # Release the lock
        lock_key = f"lock:extraction:{filename}"
        redis_client.delete(lock_key)
        
        # Could push to DLQ here for retry logic
        # redis_client.rpush(EXTRACTION_DLQ, json.dumps({**job_data, 'error': error_msg}))
        
        return False

def process_extraction_queue():
    """
    Main worker loop - process extraction jobs from the queue using atomic BLPOP.
    """
    logger.info(
        f"worker_id={worker_id} stage=extraction event=worker_started "
        f"queue={EXTRACTION_JOBS}"
    )
    
    while not shutdown_event.is_set():
        try:
            # Atomic blocking pop from extraction jobs queue (5 second timeout)
            result = redis_client.brpop(EXTRACTION_JOBS, timeout=5)
            
            if result:
                _, job_item = result
                job_data = json.loads(job_item)
                
                # Process the extraction job
                process_extraction_job(job_data)
            else:
                # No item in queue, continue waiting
                logger.debug(
                    f"worker_id={worker_id} stage=extraction event=queue_empty "
                    f"queue={EXTRACTION_JOBS}"
                )
                
        except Exception as e:
            logger.error(
                f"worker_id={worker_id} stage=extraction event=worker_error "
                f"error={str(e)}"
            )
            logger.exception("Detailed error information:")
            time.sleep(5)  # Back off on error
    
    logger.info(
        f"worker_id={worker_id} stage=extraction event=shutdown_complete"
    )


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Document extraction worker")
    parser.add_argument("--worker-id", type=str, required=True, help="Unique worker identifier")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    # Set worker ID
    worker_id = args.worker_id
    
    # Set logging level based on debug flag
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Ensure the processed directory exists
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    try:
        logger.info(f"worker_id={worker_id} stage=extraction event=starting")
        process_extraction_queue()
    except KeyboardInterrupt:
        logger.info(f"worker_id={worker_id} stage=extraction event=keyboard_interrupt")
    finally:
        # Close the database connection
        db_handler.close()
        logger.info(f"worker_id={worker_id} stage=extraction event=stopped")



