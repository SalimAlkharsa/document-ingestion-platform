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
    def __init__(self, base_dir, log_dir, venv_path=None, redis_port=6379):
        self.base_dir = Path(base_dir).absolute()
        self.log_dir, self.timestamp = setup_logging(log_dir)
        self.venv_path = venv_path
        self.redis_port = redis_port
        self.processes = {}
        self.running = False
        
    def _create_command_env(self):
        """Create environment variables for commands"""
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{self.base_dir}/platform:{env.get('PYTHONPATH', '')}"
        return env
        
    def start_redis(self):
        """Start Redis server"""
        logging.info("Starting Redis server...")
        try:
            redis_log = self.log_dir / f"redis_{self.timestamp}.log"
            process = subprocess.Popen(
                ["redis-server", "--port", str(self.redis_port)],
                stdout=open(redis_log, 'a'),  # Use append mode
                stderr=subprocess.STDOUT,
                env=self._create_command_env()
            )
            self.processes['redis'] = process
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
            
    def start_component(self, name, command):
        """Start a component process with logging"""
        # Use date for log file name, not timestamp
        component_log = self.log_dir / f"{name}_{self.timestamp}.log"
        logging.info(f"Starting {name} component...")
        
        # Check if log already exists
        log_exists = component_log.exists() and component_log.stat().st_size > 0
        
        # Build the full command with virtual environment activation (if provided)
        if self.venv_path:
            full_command = f". {self.venv_path} && export PYTHONPATH={self.base_dir}/platform && {command}"
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
            self.processes[name] = process
            logging.info(f"{name} started with PID {process.pid}, logs at {component_log}")
            return True
        except Exception as e:
            logging.error(f"Failed to start {name}: {e}")
            return False
    
    def start_pipeline(self):
        """Start all pipeline components"""
        logging.info("Starting backend pipeline...")
        self.running = True
        
        # Start Redis first
        if not self.start_redis():
            logging.error("Failed to start Redis. Exiting.")
            return False
        
        # Start all pipeline components in parallel
        components = {
            "extraction": "python3 platform/ingest_tools/extraction.py --mode=batch",
            "chunking": "python3 platform/ingest_tools/chunking.py",
            "embedding": "python3 platform/ingest_tools/embedding.py"
        }
        
        for name, cmd in components.items():
            if not self.start_component(name, cmd):
                logging.error(f"Failed to start {name}. Continuing with other components.")
        
        logging.info("All pipeline components started.")
        return True
        
    def monitor(self):
        """Monitor running processes and respawn if needed"""
        try:
            while self.running:
                for name, process in list(self.processes.items()):
                    if process.poll() is not None:
                        exit_code = process.returncode
                        if exit_code != 2:
                            logging.warning(f"{name} process exited with code {exit_code}")
                        
                        # Don't restart redis
                        if name == 'redis':
                            continue
                        
                        # Don't restart extraction if it exits with code 2 (intended behavior)
                        if name == 'extraction' and exit_code == 2:
                            continue
                        
                        # Restart other processes or extraction with other exit codes
                        logging.info(f"Attempting to restart {name}...")
                        if name == 'extraction':
                            self.start_component(name, "python3 platform/ingest_tools/extraction.py --mode=batch")
                        elif name == 'chunking':
                            self.start_component(name, "python3 platform/ingest_tools/chunking.py")
                        elif name == 'embedding':
                            self.start_component(name, "python3 platform/ingest_tools/embedding.py")
                
                time.sleep(15)
        except KeyboardInterrupt:
            logging.info("Received interrupt, shutting down...")
            self.shutdown()
            
    def shutdown(self):
        """Gracefully shutdown all processes"""
        logging.info("Shutting down pipeline components...")
        self.running = False
        
        # Terminate all processes
        for name, process in self.processes.items():
            logging.info(f"Terminating {name}...")
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logging.warning(f"{name} did not terminate gracefully, killing...")
                process.kill()
                
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
