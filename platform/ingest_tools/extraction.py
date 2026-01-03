import argparse
import os
import logging
from pathlib import Path
import shutil
import sys
import redis
import json
import datetime
from docling.document_converter import DocumentConverter

# Add the parent directory to sys.path to import globals
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from globals import MASTER_LIBRARY, PROCESSED_DIR, REDIS_QUEUE

# Import DocumentDBHandler from the db module (relative to platform directory)
sys.path.insert(0, str(project_root / 'platform'))
from db.db_handler import DocumentDBHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the document converter and Redis client
converter = DocumentConverter()
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)
db_handler = DocumentDBHandler()

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

def extract_metadata(document, file_path):
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
    
    logger.debug(f"Extracted metadata: {metadata}")
    return metadata

def add_to_queue(file_path):
    """
    Convert the document and add the result to the Redis queue.
    """
    try:
        # Update status to 'processing'
        db_handler.update_document_status(file_path, "processing")
        
        result = converter.convert(file_path)
        document = result.document
        if document:
            markdown_output = document.export_to_markdown()
            json_output = document.export_to_dict()
            
            # Extract metadata from the document
            metadata = extract_metadata(document, file_path)
            
            redis_client.rpush(REDIS_QUEUE, json.dumps({
                'file_path': file_path,
                'markdown_output': markdown_output,
                'json_output': json_output,
                'metadata': metadata
            }))
            mark_as_processed(file_path, "processed")
            return True
        else:
            error_msg = f"Failed to convert document"
            logger.error(f"{error_msg}: {file_path}")
            mark_as_processed(file_path, "error", error_msg)
            return False
    except Exception as e:
        error_msg = f"Exception during processing: {str(e)}"
        logger.error(f"{error_msg} for {file_path}")
        mark_as_processed(file_path, "error", error_msg)
        return False

def batch_extraction():
    """
    Perform batch extraction of documents from the master library.
    """
    logger.info("Starting batch extraction")
    for filename in os.listdir(MASTER_LIBRARY):
        if filename.endswith(".pdf"):
            file_path = os.path.join(MASTER_LIBRARY, filename)
            logger.info(f"Processing file: {file_path}")
            
            # Register the document in the database
            db_handler.add_document(filename, file_path, "pending")
            
            # Process the document
            add_to_queue(file_path)
    
    logger.info("Batch extraction completed")

def nightly_pipeline():
    """
    Perform nightly pipeline extraction of documents from the master library.
    Only process documents that have not been processed yet.
    """
    return -1

def run(mode):
    """
    Run the extraction script in the specified mode (batch or nightly).
    """
    logger.info(f"Running in {mode} mode")
    
    # Ensure the processed directory exists
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    try:
        if mode == "batch":
            batch_extraction()
            sys.exit(2)
        elif mode == "nightly":
            # not really tested or focused on
            nightly_pipeline()
    finally:
        # Close the database connection
        db_handler.close()

if __name__ == "__main__":
    # Parse command-line arguments to determine the mode of operation
    parser = argparse.ArgumentParser(description="Document extraction script")
    parser.add_argument("--mode", choices=["batch", "nightly"], required=True, help="Mode of operation")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    # Set logging level based on debug flag
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        
    run(args.mode)


