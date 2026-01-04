# Document Ingestion Platform

A document processing pipeline that extracts, chunks, and embeds PDFs into MongoDB for semantic search and RAG applications.

## Quick Start

```bash
# Install
./scripts/setup.sh
cp .env.example .env
# Edit .env with your MongoDB password

# Start Redis
brew services start redis  # or: redis-server

# Run pipeline
source venv/bin/activate
cp your_document.pdf data/master_library/
python platform/ingest_tools/run_platform.py

# Launch demo (optional)
streamlit run demo_app.py
```

## Prerequisites

- Python 3.10+
- Redis
- MongoDB Atlas account
- 4GB+ RAM

## Installation

1. **Setup:**

```bash
./scripts/setup.sh
```

2. **Configure MongoDB:**

```bash
cp .env.example .env
nano .env  # Add your MongoDB password
```

3. **Start Redis:**

```bash
brew install redis  # macOS
brew services start redis
```

## Usage

**Process Documents:**

```bash
source venv/bin/activate
cp *.pdf data/master_library/
python platform/ingest_tools/run_platform.py
```

**Search Demo:**

```bash
streamlit run demo_app.py
```

## Configuration

Edit `.env` or `config/config.py`:

| Variable            | Default             | Description                 |
| ------------------- | ------------------- | --------------------------- |
| `MONGO_DB_PASSWORD` | -                   | MongoDB password (required) |
| `EMBEDDING_MODEL`   | `all-mpnet-base-v2` | Embedding model             |
| `MAX_TOKENS`        | `8191`              | Max tokens per chunk        |
| `REDIS_PORT`        | `6379`              | Redis port                  |

## Project Structure

```
document-ingestion-platform/
├── config/
│   └── config.py                 # Configuration settings
├── platform/
│   ├── ingest_tools/
│   │   ├── extraction.py         # PDF extraction (Docling)
│   │   ├── chunking.py           # Document chunking (HybridChunker)
│   │   ├── embedding.py          # Vector embedding (all-mpnet-base-v2)
│   │   └── run_platform.py       # Main orchestrator
│   └── db/
│       ├── db_handler.py         # SQLite operations
│       └── mongodb_helper.py     # MongoDB + similarity search
├── data/
│   ├── master_library/           # Input PDFs
│   ├── processed/                # Chunked JSON files
│   └── local_dbs/                # SQLite databases
├── logs/                         # Application logs
├── scripts/
│   ├── setup.sh                  # Setup script
│   ├── run.sh                    # Run pipeline
│   └── run_demo.sh               # Launch Streamlit
├── demo_app.py                   # Streamlit search demo
├── .env                          # Environment config (DO NOT COMMIT)
├── .env.example                  # Template for environment config
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── LICENSE                       # MIT License
└── README.md                     # This file
```

## 🔍 Monitoring & Debugging

### Check Processing Status

```python
from document_ingestion_platform.db.db_handler import DocumentDBHandler

db = DocumentDBHandler()
stats = db.get_stats()
print(stats)
# {'total': 10, 'pending': 2, 'processing': 1, 'processed': 6, 'error': 1}
```

### View Redis Queues

```bash
redis-cli
> LLEN document_processing_queue
> LLEN embedding_queue
> LRANGE embedding_queue 0 -1
```

### Query MongoDB

```python
from document_ingestion_platform.db.mongodb_helper import MongoDBHelper

mongo = MongoDBHelper()

# Count documents
count = mongo.count_documents()
print(f"Total embedded chunks: {count}")

# Search
results = mongo.search_similar("data privacy", k=5)
for r in results:
    print(f"Score: {r['score']:.3f} - {r['text'][:100]}")
```

### View Logs

```bash
tail -f logs/extraction_*.log
tail -f logs/chunking_*.log
tail -f logs/embedding_*.log
```

## 🐛 Troubleshooting

### Redis Connection Error

**Problem:** `Cannot connect to Redis`

**Solution:**

```bash
# Start Redis
redis-server

# Or with Homebrew (macOS)
brew services start redis

# Check if running
redis-cli ping  # Should return "PONG"
```

### MongoDB Authentication Failed

**Problem:** `Authentication failed`

**Solution:** Check `.env` file has correct credentials:

```bash
MONGO_DB_PASSWORD=your_actual_password
MONGO_DB_USERNAME=your_username
```

### Module 'platform' Conflict

**Problem:** `module 'platform' has no attribute 'system'`

**Solution:** This is due to Python's built-in `platform` module conflicting with the project directory. The code handles this with proper sys.path manipulation. If you see this error, ensure you're running scripts from the project root.

### Out of Memory

**Problem:** Process killed during embedding

**Solution:** Use a smaller model or reduce batch size:

```bash
# In .env
EMBEDDING_MODEL=all-MiniLM-L6-v2  # Smaller model (384-dim)
```

### Model Download Issues

**Problem:** Error downloading model on first run

**Solution:** Ensure internet connection and disk space. Models are cached in `~/.cache/huggingface/`.

## 🚀 Performance

### Throughput

On a typical system (4 CPU cores, 8GB RAM):

- **Extraction**: ~2-5 pages/second
- **Chunking**: ~10-20 documents/second
- **Embedding**: ~30-50 chunks/second (all-mpnet-base-v2)

### Optimization Tips

1. **GPU Acceleration**: Use CUDA-enabled PyTorch for 5-10x faster embedding
2. **Parallel Workers**: Run multiple chunking/embedding workers
3. **Batch Processing**: Increase batch size for throughput
4. **Model Selection**: Balance quality vs speed based on use case

## 📝 License

MIT License - See [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 🙏 Acknowledgments

- [Docling](https://github.com/DS4SD/docling) - PDF to markdown conversion
- [SentenceTransformers](https://www.sbert.net/) - Embedding models
- [Streamlit](https://streamlit.io/) - Web interface framework
- [MongoDB](https://www.mongodb.com/) - Vector database
- [Redis](https://redis.io/) - Queue management
  platform/ingest_tools/ # Processing pipeline
  ├── extraction.py # PDF → markdown/JSON
  ├── chunking.py # Document chunking
  ├── embedding.py # Vector embeddings
  └── run_platform.py # Orchestrator
  platform/db/ # Database helpers
  data/master_library/ # Input PDFs
  logs/ # Application logs
  demo_app.py # Streamlit search demo

````

## Troubleshooting

**Redis not running:**
```bash
brew services start redis
redis-cli ping  # Should return "PONG"
````

**MongoDB auth failed:**
Check `.env` has correct `MONGO_DB_PASSWORD`

**Out of memory:**
Use smaller model in `.env`: `EMBEDDING_MODEL=all-MiniLM-L6-v2`

**Logs:**

```bash
tail -f logs/*.log
```

## License

MIT
