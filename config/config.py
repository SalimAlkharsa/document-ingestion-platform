"""
Configuration file for Document Ingestion Platform
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory of the project
BASE_DIR = Path(__file__).parent.parent.absolute()

# Directory containing the master library of documents
MASTER_LIBRARY = os.getenv("MASTER_LIBRARY", str(BASE_DIR / "data" / "master_library"))

# Directory to store processed documents
PROCESSED_DIR = os.getenv("PROCESSED_DIR", str(BASE_DIR / "data" / "processed"))

# Directory to store queued documents (if needed)
QUEUE_DIR = os.getenv("QUEUE_DIR", str(BASE_DIR / "data" / "queue"))

# Maximum tokens for the tokenizer
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8191"))  # text-embedding-3-large's maximum context length

# SQLite database settings
DB_DIR = os.getenv("DB_DIR", str(BASE_DIR / "data" / "local_dbs"))
DOCUMENTS_DB_PATH = os.getenv("DOCUMENTS_DB_PATH", str(BASE_DIR / "data" / "local_dbs" / "documents.db"))

# Redis queues
EMBEDDING_QUEUE = os.getenv("EMBEDDING_QUEUE", "embedding_queue")
REDIS_QUEUE = os.getenv("REDIS_QUEUE", "document_processing_queue")
ALL_REDIS_QUEUES = [EMBEDDING_QUEUE, REDIS_QUEUE]

# Redis connection settings
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Debug folders
CHUNKS_DEBUG_FOLDER = os.getenv("CHUNKS_DEBUG_FOLDER", str(BASE_DIR / "data" / "debug" / "chunks"))

# MongoDB settings - using environment variable for password
db_password = os.getenv("MONGO_DB_PASSWORD", "")
db_username = os.getenv("MONGO_DB_USERNAME", "galgoteamai")
db_cluster = os.getenv("MONGO_DB_CLUSTER", "devcluster.hlz3n.mongodb.net")

# MongoDB connection string with password from environment variable
MONGO_CONNECTION_STRING = os.getenv(
    "MONGO_CONNECTION_STRING",
    f"mongodb+srv://{db_username}:{db_password}@{db_cluster}/?retryWrites=true&w=majority&appName=DevCluster"
)
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "Dev0")
MONGO_EMBEDDINGS_COLLECTION = os.getenv("MONGO_EMBEDDINGS_COLLECTION", "local_debug")
VECTOR_SEARCH_INDEX = os.getenv("VECTOR_SEARCH_INDEX", "vector_index")

# Embedding model settings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TOKENIZER_MODEL = os.getenv("TOKENIZER_MODEL", "bert-base-uncased")

# Logging settings
LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def ensure_directories():
    """Create necessary directories if they don't exist"""
    directories = [
        MASTER_LIBRARY,
        PROCESSED_DIR,
        QUEUE_DIR,
        DB_DIR,
        CHUNKS_DEBUG_FOLDER,
        LOG_DIR
    ]

    for directory in directories:
        os.makedirs(directory, exist_ok=True)

    print(f"✓ All required directories created/verified")


if __name__ == "__main__":
    # When run directly, create all directories and show configuration
    ensure_directories()

    print("\n" + "="*60)
    print("Document Ingestion Platform Configuration")
    print("="*60)
    print(f"Base Directory: {BASE_DIR}")
    print(f"Master Library: {MASTER_LIBRARY}")
    print(f"Processed Dir: {PROCESSED_DIR}")
    print(f"Database Dir: {DB_DIR}")
    print(f"Log Dir: {LOG_DIR}")
    print(f"MongoDB Database: {MONGO_DB_NAME}")
    print(f"MongoDB Collection: {MONGO_EMBEDDINGS_COLLECTION}")
    print(f"Redis Host: {REDIS_HOST}:{REDIS_PORT}")
    print(f"Embedding Model: {EMBEDDING_MODEL}")
    print("="*60)
