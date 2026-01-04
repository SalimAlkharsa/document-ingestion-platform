# Document Ingestion Platform

A high-performance document processing pipeline that extracts, chunks, and embeds PDFs into MongoDB for semantic search and RAG applications. Built with parallel processing, Redis task queues, and optimized for heavy weight use.

## Quick Start

```bash
# 1. Setup environment
./scripts/setup.sh
cp .env.example .env
# Edit .env with your MongoDB credentials

# 2. Start Redis
brew services start redis  # macOS
# OR: redis-server

# 3. Process documents
source venv/bin/activate
cp your_document.pdf data/master_library/
python document_ingestion_platform/ingest_tools/run_platform.py

# 4. Launch search demo (optional)
streamlit run demo_app.py
```

## Prerequisites

- **Python 3.10+**
- **Redis** (task queue and caching)
- **MongoDB Atlas** account (vector storage)
- **4GB+ RAM** (8GB+ recommended for good UX)

## Installation

### 1. Clone and Setup

```bash
git clone <repository-url>
cd document-ingestion-platform
./scripts/setup.sh
```

This script will:

- Create a Python virtual environment
- Install all dependencies from `requirements.txt`
- Set up the basic project structure

### 2. Configure Environment

```bash
cp .env.example .env
nano .env  # or your preferred editor
```

**Required settings:**

```bash
# MongoDB Configuration
MONGO_DB_PASSWORD=your_mongodb_password
MONGO_DB_USERNAME=your_username  # Optional, defaults to 'document_ingestion'

# Optional: Customize these
EMBEDDING_MODEL=all-mpnet-base-v2  # Or: all-MiniLM-L6-v2 (faster, smaller)
MAX_TOKENS=8191
REDIS_PORT=6379
```

### 3. Start Redis

**macOS:**

```bash
brew install redis
brew services start redis
```

## Usage

### Basic Document Processing

```bash
# Activate virtual environment
source venv/bin/activate

# Copy PDFs to the master library
cp /path/to/your/document.pdf data/master_library/

# Run the ingestion pipeline
python document_ingestion_platform/ingest_tools/run_platform.py
```

The pipeline will automatically:

1. **Extract** PDF content to markdown/JSON (using Docling)
2. **Chunk** documents into semantic segments
3. **Embed** chunks using SentenceTransformers
4. **Store** vectors in MongoDB for similarity search

### Advanced Usage

**Run with custom worker configuration:**

```bash
# Edit worker_config.py to adjust parallel processing
python document_ingestion_platform/ingest_tools/run_platform.py --workers 4
```

**Process specific documents:**

```bash
# Only process new documents (skip already processed)
python document_ingestion_platform/ingest_tools/run_platform.py --skip-processed
```

**Monitor pipeline in real-time:**

```bash
# In a separate terminal
./monitor_pipeline.sh
```

### Search Demo Application

Launch the Streamlit web interface for semantic search:

```bash
streamlit run demo_app.py
```

Features:

- Semantic search across all embedded documents
- Adjustable result count and similarity threshold
- Source document tracking
- Chunk metadata display
- Useful to check pipeline behavior via a frontend UI

## Configuration

### Environment Variables

Edit `.env` file or set environment variables:

| Variable            | Default               | Description                           |
| ------------------- | --------------------- | ------------------------------------- |
| `MONGO_DB_PASSWORD` | -                     | MongoDB password (required)           |
| `MONGO_DB_USERNAME` | `document_ingestion`  | MongoDB username                      |
| `MONGO_DB_NAME`     | `document_db`         | MongoDB database name                 |
| `MONGO_COLLECTION`  | `document_embeddings` | MongoDB collection name               |
| `EMBEDDING_MODEL`   | `all-mpnet-base-v2`   | Embedding model (768-dim)             |
| `MAX_TOKENS`        | `8191`                | Max tokens per chunk                  |
| `REDIS_HOST`        | `localhost`           | Redis host                            |
| `REDIS_PORT`        | `6379`                | Redis port                            |
| `MASTER_LIBRARY`    | `data/master_library` | Input PDF directory                   |
| `PROCESSED_DIR`     | `data/processed`      | Output directory for processed chunks |

### Worker Configuration

Edit `config/worker_config.py` to adjust parallel processing:

```python
WORKER_CONFIG = {
    'chunking_workers': 2,    # Parallel chunking workers
    'embedding_workers': 2,   # Parallel embedding workers
}
```

**Recommendations:**

- **CPU cores**: Set `chunking_workers = CPU_cores / 2`
- **GPU available**: Increase `embedding_workers` to 4-8
- **8GB RAM**: Use `chunking_workers=2, embedding_workers=2`
- **16GB+ RAM**: Use `chunking_workers=4, embedding_workers=4`

### Model Selection

**all-mpnet-base-v2** (Default):

- 768-dimensional vectors
- Best accuracy for semantic search
- Slower (~30-50 chunks/sec)

**all-MiniLM-L6-v2** (Faster):

- 384-dimensional vectors
- Good accuracy, 2-3x faster
- Recommended for large datasets

```bash
# In .env
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

## Project Structure

```
document-ingestion-platform/
├── document_ingestion_platform/       # Main package
│   ├── __init__.py
│   ├── ingest_tools/                  # Processing pipeline
│   │   ├── __init__.py
│   │   ├── extraction.py              # PDF extraction (Docling)
│   │   ├── chunking.py                # Document chunking (HybridChunker)
│   │   ├── embedding.py               # Vector embedding (SentenceTransformers)
│   │   ├── extraction_manager.py      # Extraction orchestration
│   │   └── run_platform.py            # Main pipeline orchestrator
│   └── db/                            # Database layer
│       ├── __init__.py
│       ├── db_handler.py              # SQLite operations (document tracking)
│       └── mongodb_helper.py          # MongoDB + vector similarity search
│
├── config/                            # Configuration
│   ├── config.py                      # Environment settings
│   └── worker_config.py               # Worker/performance tuning
│
├── data/                              # Data directories
│   ├── master_library/                # Input: Place PDFs here
│   ├── processed/                     # Output: Chunked JSON files
│   │   └── simulated_vector_store/    # Simulated vector store (for testing)
│   ├── queue/                         # Queue directory for processing
│   ├── local_dbs/                     # SQLite databases
│   │   └── documents.db               # Document processing status
│   └── debug/                         # Debug output
│       └── chunks/                    # Debug chunk files
│
├── logs/                              # Application logs
│   ├── extraction_*.log               # Extraction worker logs
│   ├── chunking_*.log                 # Chunking worker logs
│   ├── embedding_*.log                # Embedding worker logs
│   └── manager.log                    # Main orchestrator log
│
├── benchmarks/                        # Performance benchmarks
│   └── results/                       # Benchmark results
│       ├── config_1_workers/
│       ├── config_2_workers/
│       ├── config_4_workers/
│       └── config_8_workers/
│
├── scripts/                           # Utility scripts
│   ├── setup.sh                       # Installation script
│   ├── run.sh                         # Run pipeline script
│   └── run_demo.sh                    # Launch Streamlit demo
│
├── demo_app.py                        # Streamlit search interface
├── globals.py                         # Global constants
├── requirements.txt                   # Python dependencies
├── .env                               # Environment config (DO NOT COMMIT)
├── .env.example                       # Environment config template
├── .gitignore                         # Git ignore rules
├── LICENSE                            # MIT License
├── README.md                          # This file
├── QUICKSTART.md                      # Quick start guide
└── PROJECT_NOTES_FOR_RESUME.md        # Project documentation
```

### Key Components

**Extraction Pipeline** ([document_ingestion_platform/ingest_tools/extraction.py](document_ingestion_platform/ingest_tools/extraction.py)):

- Converts PDFs to markdown using Docling
- Extracts text, tables, and document structure
- Handles OCR for scanned documents

**Chunking** ([document_ingestion_platform/ingest_tools/chunking.py](document_ingestion_platform/ingest_tools/chunking.py)):

- Splits documents into semantic chunks
- Preserves context across chunk boundaries
- Configurable chunk size and overlap

**Embedding** ([document_ingestion_platform/ingest_tools/embedding.py](document_ingestion_platform/ingest_tools/embedding.py)):

- Generates vector embeddings using SentenceTransformers
- Batch processing for efficiency
- Stores vectors in MongoDB with metadata

**Database Layer**:

- **SQLite** ([db_handler.py](document_ingestion_platform/db/db_handler.py)): Document status tracking
- **MongoDB** ([mongodb_helper.py](document_ingestion_platform/db/mongodb_helper.py)): Vector storage and similarity search
- **Redis**: Task queues for parallel processing
  ├── scripts/
  │ ├── setup.sh # Setup script
  │ ├── run.sh # Run pipeline
  │ └── run_demo.sh # Launch Streamlit
  ├── demo_app.py # Streamlit search demo
  ├── .env # Environment config (DO NOT COMMIT)
  ├── .env.example # Template for environment config
  ├── .gitignore # Git ignore rules
  ├── requirements.txt # Python dependencies
  ├── LICENSE # MIT License
  └── README.md # This file

````

## 🔍 Monitoring & Debugging

### Check Processing Status

```python
from document_ingestion_platform.db.db_handler import DocumentDBHandler

db = DocumentDBHandler()
stats = db.get_stats()
print(stats)
# Output: {'total': 10, 'pending': 2, 'processing': 1, 'processed': 6, 'error': 1}
````

### Monitor Redis Queues

```bash
redis-cli
> LLEN document_processing_queue
(integer) 5
> LLEN embedding_queue
(integer) 23
> LRANGE embedding_queue 0 -1
```

### Search MongoDB

```python
from document_ingestion_platform.db.mongodb_helper import MongoDBHelper

mongo = MongoDBHelper()

# Count embedded chunks
count = mongo.count_documents()
print(f"Total embedded chunks: {count}")

# Semantic search
results = mongo.search_similar("data privacy and security", k=5)
for r in results:
    print(f"Score: {r['score']:.3f}")
    print(f"Text: {r['text'][:100]}...")
    print(f"Source: {r['metadata']['source_file']}\n")
```

### View Logs

```bash
# All logs
tail -f logs/*.log

# Specific component
tail -f logs/extraction_*.log
tail -f logs/chunking_*.log
tail -f logs/embedding_*.log
tail -f logs/manager.log
```

### Real-time Monitoring

```bash

## � Technical Stack

### Core Dependencies

- **[Docling](https://github.com/DS4SD/docling)** (v2.25.0) - Advanced PDF extraction with layout understanding
- **[SentenceTransformers](https://www.sbert.net/)** (v3.4.1) - State-of-the-art text embeddings
- **[PyMongo](https://pymongo.readthedocs.io/)** (v4.11.2) - MongoDB driver with vector search
- **[Redis-py](https://redis-py.readthedocs.io/)** (v5.2.1) - Task queue management
- **[Streamlit](https://streamlit.io/)** (v1.41.1) - Interactive web UI
- **[PyTorch](https://pytorch.org/)** (v2.6.0) - Deep learning framework
- **[Transformers](https://huggingface.co/transformers/)** (v4.49.0) - Hugging Face transformers

### Architecture

```

┌─────────────────┐
│ Master Library │ ← Input PDFs
└────────┬────────┘
│
▼
┌─────────────────┐
│ Extraction │ → Docling PDF extraction
│ Workers │
└────────┬────────┘
│
▼
┌─────────────────┐
│ Redis Queue │ ← Task distribution
└────────┬────────┘
│
▼
┌─────────────────┐
│ Chunking │ → Semantic segmentation
│ Workers │
└────────┬────────┘
│
▼
┌─────────────────┐
│ Embedding │ → Vector generation
│ Workers │
└────────┬────────┘
│
▼
┌─────────────────┐
│ MongoDB │ ← Vector storage + search
└─────────────────┘
│
▼
┌─────────────────┐
│ Streamlit Demo │ → Semantic search UI
└─────────────────┘

````

## 🔧 Advanced Features

### Custom Chunking Strategy

Edit [document_ingestion_platform/ingest_tools/chunking.py](document_ingestion_platform/ingest_tools/chunking.py):

```python
# Adjust chunk size and overlap
CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50  # tokens
````

### Custom Embedding Model

Any SentenceTransformers-compatible model:

```bash
# In .env
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
# Or OpenAI-compatible models (requires API key)
```

### Model Download Issues

**Problem:** Error downloading model on first run

**Solution:** Ensure internet connection and disk space. Models are cached in `~/.cache/huggingface/`.

## 📝 License

MIT License - See [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📖 Additional Documentation

- [QUICKSTART.md](QUICKSTART.md) - Detailed setup guide
- [PROJECT_NOTES_FOR_RESUME.md](PROJECT_NOTES_FOR_RESUME.md) - Project overview and achievements
- [config/worker_config.py](config/worker_config.py) - Worker configuration details
- [benchmarks/RESULTS.md](benchmarks/RESULTS.md) - Benchmark results and analysis

## 🙏 Acknowledgments

- **[Docling](https://github.com/DS4SD/docling)** - Enterprise-grade PDF extraction
- **[SentenceTransformers](https://www.sbert.net/)** - Powerful embedding models
- **[MongoDB](https://www.mongodb.com/)** - Scalable vector database
- **[Redis](https://redis.io/)** - High-performance task queues
- **[Streamlit](https://streamlit.io/)** - Rapid UI development

## 📧 Support

For issues, questions, or contributions:

- Open an issue on GitHub
- Review logs in `logs/` directory for debugging

---
