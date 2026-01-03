# Quick Start Guide

## 5-Minute Setup

### 1. Install Dependencies

```bash
./scripts/setup.sh
```

This creates a virtual environment and installs all required packages.

### 2. Configure Environment

```bash
cp .env.example .env
nano .env  # or use your favorite editor
```

**Minimum required:** Set your MongoDB password:
```
MONGO_DB_PASSWORD=your_actual_password
```

### 3. Start Redis

**macOS:**
```bash
brew install redis
redis-server
```

**Ubuntu:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**Docker:**
```bash
docker run -d -p 6379:6379 redis:latest
```

### 4. Test Setup

```bash
python3 scripts/test_setup.py
```

You should see:
```
✓ PASS   Imports
✓ PASS   Configuration
✓ PASS   Directories
✓ PASS   Redis
✓ PASS   MongoDB
```

### 5. Add Documents

```bash
cp your_document.pdf data/master_library/
```

### 6. Run Platform

```bash
source venv/bin/activate
python3 platform/ingest_tools/run_platform.py
```

Or use the helper script:
```bash
./scripts/run.sh
```

## What Happens Next?

The platform will:
1. **Extract** your PDF to markdown/JSON
2. **Chunk** it into semantic segments
3. **Embed** each chunk with vector embeddings
4. **Store** everything in MongoDB

Monitor progress:
```bash
tail -f logs/pipeline_main_*.log
```

## Troubleshooting

### Redis Not Running
```
Error: Cannot connect to Redis
```
**Fix:** Start Redis with `redis-server`

### MongoDB Authentication Failed
```
Error: Authentication failed
```
**Fix:** Check `MONGO_DB_PASSWORD` in `.env`

### Dependencies Not Installed
```
ModuleNotFoundError: No module named 'docling'
```
**Fix:** Run `./scripts/setup.sh` or `pip install -r requirements.txt`

## What's Next?

- Check the full [README.md](README.md) for detailed documentation
- View logs in the `logs/` directory
- Query your embeddings in MongoDB
- Build search/RAG applications on top

## Architecture Overview

```
PDF Files → Extraction → Chunking → Embedding → MongoDB
            (Docling)    (Hybrid)   (SBERT)    (Atlas)
                ↓           ↓          ↓
             Redis      Redis     Vector DB
```

Enjoy your document ingestion platform! 🚀
