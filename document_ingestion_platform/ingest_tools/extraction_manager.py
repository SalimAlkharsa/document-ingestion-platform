"""
Extraction Manager - Orchestrates document extraction by scanning master library
and creating extraction jobs for workers to process.

This manager prevents race conditions by using atomic Redis locks to claim files
before creating extraction jobs.
"""
import os
import logging
import argparse
import sys
import redis
import json
import time
import signal
import threading
from pathlib import Path
from datetime import datetime

# Add the parent directory to sys.path to import globals
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from globals import MASTER_LIBRARY, EXTRACTION_JOBS, generate_trace_id

# Import DocumentDBHandler from the db module
sys.path.insert(0, str(project_root / 'platform'))
from document_ingestion_platform.db.db_handler import DocumentDBHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Redis client and DB handler
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)
db_handler = DocumentDBHandler()

# Shutdown event for graceful termination
shutdown_event = threading.Event()


def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info("event=shutdown_requested signal=SIGTERM/SIGINT")
    shutdown_event.set()


# Register signal handlers
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)


class ExtractionManager:
    """
    Manages extraction job creation by scanning master library and
    creating extraction jobs with atomic locking.
    """
    
    def __init__(self, scan_interval=30, lock_ttl=300):
        """
        Initialize the extraction manager.
        
        Args:
            scan_interval: Seconds between master library scans
            lock_ttl: Time-to-live for file locks in seconds
        """
        self.scan_interval = scan_interval
        self.lock_ttl = lock_ttl
        self.manager_id = "extraction-manager"
        logger.info(
            f"manager_id={self.manager_id} event=initialized "
            f"scan_interval={scan_interval}s lock_ttl={lock_ttl}s"
        )
    
    def is_file_locked(self, filename):
        """Check if a file is currently locked by any worker"""
        lock_key = f"lock:extraction:{filename}"
        return redis_client.exists(lock_key) > 0
    
    def is_file_processed(self, filepath):
        """Check if file has already been processed in the database"""
        status = db_handler.get_document_status(filepath)
        return status in ["processed", "processing"]
    
    def claim_file(self, filename):
        """
        Attempt to claim a file for extraction using atomic Redis lock.
        
        Returns:
            True if successfully claimed, False otherwise
        """
        lock_key = f"lock:extraction:{filename}"
        # Use SETNX (SET if Not eXists) with TTL for atomic lock
        claimed = redis_client.set(
            lock_key, 
            self.manager_id, 
            nx=True,  # Only set if doesn't exist
            ex=self.lock_ttl  # Expire after TTL seconds
        )
        
        if claimed:
            logger.debug(f"manager_id={self.manager_id} event=file_claimed file={filename}")
            return True
        else:
            logger.debug(f"manager_id={self.manager_id} event=file_already_locked file={filename}")
            return False
    
    def create_extraction_job(self, file_path, filename, trace_id):
        """
        Create an extraction job and push to the extraction jobs queue.
        
        Args:
            file_path: Absolute path to the PDF file
            filename: Name of the file
            trace_id: Unique trace ID for this document
        """
        job_payload = {
            "trace_id": trace_id,
            "file_path": file_path,
            "filename": filename,
            "job_timestamp": time.time(),
            "job_created": datetime.now().isoformat(),
            "metadata": {
                "source": "master_library",
                "manager_id": self.manager_id
            }
        }
        
        # Register document in database with trace_id
        db_handler.add_document(filename, file_path, status="queued", trace_id=trace_id)
        
        # Push job to extraction queue
        redis_client.rpush(EXTRACTION_JOBS, json.dumps(job_payload))
        
        logger.info(
            f"trace_id={trace_id} manager_id={self.manager_id} event=job_created "
            f"file={filename} queue={EXTRACTION_JOBS}"
        )
    
    def scan_master_library(self):
        """
        Scan the master library for PDF files and create extraction jobs.
        
        Returns:
            Number of jobs created in this scan
        """
        if not os.path.exists(MASTER_LIBRARY):
            logger.warning(
                f"manager_id={self.manager_id} event=master_library_not_found "
                f"path={MASTER_LIBRARY}"
            )
            return 0
        
        jobs_created = 0
        files_found = 0
        files_skipped = 0
        
        logger.info(
            f"manager_id={self.manager_id} event=scan_started "
            f"path={MASTER_LIBRARY}"
        )
        
        try:
            for filename in os.listdir(MASTER_LIBRARY):
                if not filename.endswith(".pdf"):
                    continue
                
                files_found += 1
                file_path = os.path.join(MASTER_LIBRARY, filename)
                
                # Skip if already processed
                if self.is_file_processed(file_path):
                    logger.debug(
                        f"manager_id={self.manager_id} event=file_already_processed "
                        f"file={filename}"
                    )
                    files_skipped += 1
                    continue
                
                # Skip if currently locked (being processed)
                if self.is_file_locked(filename):
                    logger.debug(
                        f"manager_id={self.manager_id} event=file_locked "
                        f"file={filename}"
                    )
                    files_skipped += 1
                    continue
                
                # Try to claim the file
                if self.claim_file(filename):
                    # Generate trace ID for this document
                    trace_id = generate_trace_id()
                    
                    # Create extraction job
                    self.create_extraction_job(file_path, filename, trace_id)
                    jobs_created += 1
                else:
                    files_skipped += 1
        
        except Exception as e:
            logger.error(
                f"manager_id={self.manager_id} event=scan_error error={str(e)}"
            )
        
        logger.info(
            f"manager_id={self.manager_id} event=scan_completed "
            f"files_found={files_found} jobs_created={jobs_created} "
            f"files_skipped={files_skipped}"
        )
        
        return jobs_created
    
    def run(self):
        """
        Main loop - continuously scan master library and create extraction jobs.
        """
        logger.info(
            f"manager_id={self.manager_id} event=manager_started "
            f"scan_interval={self.scan_interval}s"
        )
        
        while not shutdown_event.is_set():
            try:
                # Scan master library and create jobs
                self.scan_master_library()
                
                # Wait for next scan interval (with interruptible sleep)
                for _ in range(self.scan_interval):
                    if shutdown_event.is_set():
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(
                    f"manager_id={self.manager_id} event=error error={str(e)}"
                )
                logger.exception("Detailed error information:")
                time.sleep(5)  # Back off on error
        
        logger.info(
            f"manager_id={self.manager_id} event=shutdown_complete"
        )


def main():
    """Main entry point for extraction manager"""
    parser = argparse.ArgumentParser(description="Extraction Manager - Creates extraction jobs")
    parser.add_argument(
        "--scan-interval", 
        type=int, 
        default=30, 
        help="Interval between scans in seconds (default: 30)"
    )
    parser.add_argument(
        "--lock-ttl", 
        type=int, 
        default=300, 
        help="Lock TTL in seconds (default: 300)"
    )
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Enable debug logging"
    )
    args = parser.parse_args()
    
    # Configure logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run manager
    manager = ExtractionManager(
        scan_interval=args.scan_interval,
        lock_ttl=args.lock_ttl
    )
    
    try:
        manager.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        db_handler.close()


if __name__ == "__main__":
    main()
