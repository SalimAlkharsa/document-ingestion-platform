"""
Worker Configuration for Document Ingestion Platform
Defines worker pool sizes and operational parameters
"""

# Worker pool sizes
WORKER_CONFIG = {
    # Manager - singleton for extraction orchestration
    'extraction_manager': 1,
    
    # Extraction workers - process PDF conversion
    'extraction_workers': 3,
    
    # Chunking workers - process document chunking
    'chunking_workers': 2,
    
    # Embedding workers - generate and store embeddings
    'embedding_workers': 2,
}

# Queue timeouts (seconds)
QUEUE_TIMEOUT = 5

# Lock TTL for extraction claims (seconds)
EXTRACTION_LOCK_TTL = 300  # 5 minutes

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds, exponential backoff

# Manager scan interval (seconds)
MANAGER_SCAN_INTERVAL = 30

# Shutdown grace period (seconds)
SHUTDOWN_GRACE_PERIOD = 60

# Document serialization format
DOC_SERIALIZATION = 'json'  # or 'pickle'

# Debug mode
DEBUG_MODE = False

# Component-specific settings
COMPONENT_SETTINGS = {
    'extraction': {
        'enabled': True,
        'log_level': 'INFO',
    },
    'chunking': {
        'enabled': True,
        'log_level': 'INFO',
    },
    'embedding': {
        'enabled': True,
        'log_level': 'INFO',
    }
}
