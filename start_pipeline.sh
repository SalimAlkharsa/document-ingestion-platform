#!/bin/bash
# Quick Start Script for Multi-Worker Pipeline

echo "======================================"
echo "Multi-Worker Pipeline - Quick Start"
echo "======================================"
echo ""

# Check if we're in the right directory
if [ ! -f "document_ingestion_platform/ingest_tools/run_platform.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

echo "✓ Running from project root"
echo ""

# Detect and activate virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
    echo "✓ Virtual environment activated"
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "⚠️  Warning: No virtual environment found (venv/ or .venv/)"
    echo "   Using system Python - consider creating a venv"
fi
echo ""

# Check if Redis is installed
if ! command -v redis-server &> /dev/null; then
    echo "❌ Redis not found. Please install Redis:"
    echo "   macOS: brew install redis"
    echo "   Linux: sudo apt-get install redis-server"
    exit 1
fi

echo "✓ Redis is installed"
echo ""

# Check Python
if ! command -v python &> /dev/null; then
    echo "❌ Python not found"
    exit 1
fi

echo "✓ Python is available: $(which python)"
echo ""

# Ensure directories exist
echo "Creating required directories..."
python -c "from config.config import ensure_directories; ensure_directories()"
echo "✓ Directories created"
echo ""

# Show current configuration
echo "Current Worker Configuration:"
echo "----------------------------"
python -c "
from config.worker_config import WORKER_CONFIG
print(f'  Extraction Manager: {WORKER_CONFIG[\"extraction_manager\"]}')
print(f'  Extraction Workers: {WORKER_CONFIG[\"extraction_workers\"]}')
print(f'  Chunking Workers: {WORKER_CONFIG[\"chunking_workers\"]}')
print(f'  Embedding Workers: {WORKER_CONFIG[\"embedding_workers\"]}')
"
echo ""

# Count PDFs in master library
PDF_COUNT=$(find data/master_library -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
echo "Documents in master library: $PDF_COUNT PDF files"
echo ""

# Check if there are PDFs to process
if [ "$PDF_COUNT" -eq 0 ]; then
    echo "⚠️  Warning: No PDF files found in data/master_library"
    echo "   Add some PDF files before starting the pipeline"
    echo ""
fi

# Ask user if they want to start
read -p "Start the multi-worker pipeline? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Starting multi-worker pipeline..."
echo "================================="
echo ""
echo "Logs will be in: logs/"
echo "Press Ctrl+C to stop"
echo ""
echo "Useful commands while running:"
echo "  Monitor logs: tail -f logs/pipeline_main_*.log"
echo "  Check queue: redis-cli LLEN extraction_jobs"
echo "  Find trace: grep 'trace_id=XXX' logs/*.log"
echo ""

# Start the pipeline
python document_ingestion_platform/ingest_tools/run_platform.py
