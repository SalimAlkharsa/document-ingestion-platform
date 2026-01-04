#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import logging
import argparse
import signal
import datetime
from pathlib import Path

# Add the parent directory to sys.path to import config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.worker_config import WORKER_CONFIG, MANAGER_SCAN_INTERVAL, EXTRACTION_LOCK_TTL

# Configure logging
def setup_logging(log_dir):
    """Set up logging configuration"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d")  # Just use date, not time
    log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True, parents=True)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    root_logger.addHandler(console)
    
    # File handler for main process
    main_log_file = log_dir / f"pipeline_main_{timestamp}.log"
    file_handler = logging.FileHandler(main_log_file, mode='a')  # Use append mode
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    
    # Log restart information if file already exists and has content
    if main_log_file.exists() and main_log_file.stat().st_size > 0:
        logging.info("=" * 50)
        logging.info(f"Pipeline restarted at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info("=" * 50)
    
    return log_dir, timestamp

class BackendPipeline:
    def __init__(self, base_dir, log_dir, venv_path=None, redis_port=6379, worker_config=None):
        self.base_dir = Path(base_dir).absolute()
        self.log_dir, self.timestamp = setup_logging(log_dir)
        self.venv_path = venv_path
        self.redis_port = redis_port
        self.worker_config = worker_config or WORKER_CONFIG
        self.processes = {}
        self.running = False
        
    def _create_command_env(self):
        """Create environment variables for commands"""
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{self.base_dir}:{env.get('PYTHONPATH', '')}"
        return env
        
    def start_redis(self):
        """Start Redis server"""
        logging.info("Starting Redis server...")
        try:
            redis_log = self.log_dir / f"redis_{self.timestamp}.log"
            redis_log_file = open(redis_log, 'a')  # Store file handle
            process = subprocess.Popen(
                ["redis-server", "--port", str(self.redis_port)],
                stdout=redis_log_file,
                stderr=subprocess.STDOUT,
                env=self._create_command_env()
            )
            self.processes['redis'] = {
                'process': process,
                'name': 'redis',
                'worker_id': None,
                'command': 'redis-server',
                'log_file': redis_log_file
            }
            logging.info(f"Redis server started with PID {process.pid}, logs at {redis_log}")
            time.sleep(2)  # Give Redis time to start
            
            # Check if Redis is running
            if process.poll() is not None:
                logging.error("Redis server failed to start!")
                return False
                
            return True
        except Exception as e:
            logging.error(f"Failed to start Redis: {e}")
            return False
            
    def start_component(self, name, command, worker_id=None):
        """Start a component process with logging"""
        # Use date for log file name, not timestamp
        log_name = f"{name}_{worker_id}_{self.timestamp}" if worker_id else f"{name}_{self.timestamp}"
        component_log = self.log_dir / f"{log_name}.log"
        
        display_name = f"{name}[{worker_id}]" if worker_id else name
        logging.info(f"Starting {display_name} component...")
        
        # Check if log already exists
        log_exists = component_log.exists() and component_log.stat().st_size > 0
        
        # Build the full command with virtual environment activation (if provided)
        if self.venv_path:
            full_command = f". {self.venv_path} && export PYTHONPATH={self.base_dir} && {command}"
        else:
            full_command = command
        
        try:
            # Open in append mode
            log_file = open(component_log, 'a')
            
            # Write restart marker if the log file already exists
            if log_exists:
                log_file.write("\n" + "=" * 50 + "\n")
                log_file.write(f"Process restarted at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write("=" * 50 + "\n\n")
                log_file.flush()
            
            process = subprocess.Popen(
                full_command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                shell=True,
                env=self._create_command_env()
            )
            
            # Store process with unique key
            process_key = f"{name}:{worker_id}" if worker_id else name
            self.processes[process_key] = {
                'process': process,
                'name': name,
                'worker_id': worker_id,
                'command': command,
                'log_file': log_file
            }
            
            logging.info(f"{display_name} started with PID {process.pid}, logs at {component_log}")
            return True
        except Exception as e:
            logging.error(f"Failed to start {display_name}: {e}")
            return False
    
    def start_extraction_manager(self):
        """Start the extraction manager (singleton)"""
        command = (
            f"python3 document_ingestion_platform/ingest_tools/extraction_manager.py "
            f"--scan-interval {MANAGER_SCAN_INTERVAL} "
            f"--lock-ttl {EXTRACTION_LOCK_TTL}"
        )
        return self.start_component("extraction-manager", command)
    
    def start_extraction_workers(self):
        """Start extraction worker pool"""
        num_workers = self.worker_config.get('extraction_workers', 3)
        logging.info(f"Starting {num_workers} extraction workers...")
        
        for i in range(num_workers):
            worker_id = f"extraction-worker-{i}"
            command = f"python3 document_ingestion_platform/ingest_tools/extraction.py --worker-id {worker_id}"
            self.start_component("extraction-worker", command, worker_id)
        
        return True
    
    def start_chunking_workers(self):
        """Start chunking worker pool"""
        num_workers = self.worker_config.get('chunking_workers', 2)
        logging.info(f"Starting {num_workers} chunking workers...")
        
        for i in range(num_workers):
            worker_id = f"chunking-worker-{i}"
            command = f"python3 document_ingestion_platform/ingest_tools/chunking.py --worker-id {worker_id}"
            self.start_component("chunking-worker", command, worker_id)
        
        return True
    
    def start_embedding_workers(self):
        """Start embedding worker pool"""
        num_workers = self.worker_config.get('embedding_workers', 2)
        logging.info(f"Starting {num_workers} embedding workers...")
        
        for i in range(num_workers):
            worker_id = f"embedding-worker-{i}"
            command = f"python3 document_ingestion_platform/ingest_tools/embedding.py --worker-id {worker_id}"
            self.start_component("embedding-worker", command, worker_id)
        
        return True
    
    def start_pipeline(self):
        """Start all pipeline components with multi-worker support"""
        logging.info("Starting multi-worker backend pipeline...")
        logging.info(f"Worker configuration: {self.worker_config}")
        self.running = True
        
        # Start Redis first
        if not self.start_redis():
            logging.error("Failed to start Redis. Exiting.")
            return False
        
        # Start extraction manager (singleton orchestrator)
        if not self.start_extraction_manager():
            logging.error("Failed to start extraction manager. Exiting.")
            return False
        
        time.sleep(1)  # Give manager time to initialize
        
        # Start worker pools
        self.start_extraction_workers()
        self.start_chunking_workers()
        self.start_embedding_workers()
        
        logging.info(f"All pipeline components started. Total workers: "
                    f"{self.worker_config['extraction_workers']} extraction + "
                    f"{self.worker_config['chunking_workers']} chunking + "
                    f"{self.worker_config['embedding_workers']} embedding")
        return True
        
    def monitor(self):
        """Monitor running processes and respawn if needed"""
        try:
            while self.running:
                for process_key, proc_info in list(self.processes.items()):
                    process = proc_info['process']
                    name = proc_info['name']
                    worker_id = proc_info['worker_id']
                    command = proc_info['command']
                    
                    display_name = f"{name}[{worker_id}]" if worker_id else name
                    
                    if process.poll() is not None:
                        exit_code = process.returncode
                        
                        if exit_code != 0:
                            logging.warning(f"{display_name} exited with code {exit_code}")
                        
                        # Don't restart redis
                        if name == 'redis':
                            continue
                        
                        # Restart workers automatically
                        logging.info(f"Attempting to restart {display_name}...")
                        
                        # Close old log file
                        proc_info['log_file'].close()
                        
                        # Remove from processes dict
                        del self.processes[process_key]
                        
                        # Restart the component
                        self.start_component(name, command, worker_id)
                
                time.sleep(15)
        except KeyboardInterrupt:
            logging.info("Received interrupt, shutting down...")
            self.shutdown()
            
    def shutdown(self):
        """Gracefully shutdown all processes"""
        logging.info("Shutting down pipeline components...")
        self.running = False
        
        # Terminate all processes
        for process_key, proc_info in self.processes.items():
            process = proc_info['process']
            name = proc_info['name']
            worker_id = proc_info['worker_id']
            display_name = f"{name}[{worker_id}]" if worker_id else name
            
            logging.info(f"Terminating {display_name}...")
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logging.warning(f"{display_name} did not terminate gracefully, killing...")
                process.kill()
            
            # Close log file
            if 'log_file' in proc_info:
                proc_info['log_file'].close()
                
        logging.info("All processes terminated.")

def main():
    parser = argparse.ArgumentParser(description="Run backend processing pipeline")
    parser.add_argument("--base-dir", default=os.getcwd(), help="Base directory of the project")
    parser.add_argument("--log-dir", default="logs", help="Directory to store logs")
    parser.add_argument("--venv", help="Path to virtual environment activate script")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis server port")
    args = parser.parse_args()
    
    # Handle Ctrl+C and termination signal
    def signal_handler(sig, frame):
        if pipeline:
            logging.info("Received termination signal...")
            pipeline.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the pipeline
    pipeline = BackendPipeline(
        base_dir=args.base_dir,
        log_dir=args.log_dir,
        venv_path=args.venv,
        redis_port=args.redis_port
    )
    
    if pipeline.start_pipeline():
        pipeline.monitor()
    else:
        logging.error("Failed to start pipeline")
        sys.exit(1)

if __name__ == "__main__":
    main()
