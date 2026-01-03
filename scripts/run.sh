#!/bin/bash
# Run script for Document Ingestion Platform

set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Run setup.sh first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Copy .env.example to .env and configure it."
    exit 1
fi

# Parse command line arguments
MODE="${1:-batch}"
DEBUG_FLAG=""

if [ "$2" = "--debug" ]; then
    DEBUG_FLAG="--debug"
fi

echo "================================================"
echo "Document Ingestion Platform - Starting"
echo "================================================"
echo "Mode: $MODE"
echo "Project Dir: $PROJECT_DIR"
echo ""

# Check Redis
echo "Checking Redis connection..."
if ! redis-cli ping &> /dev/null; then
    echo "Error: Cannot connect to Redis. Is it running?"
    echo "Start Redis with: redis-server"
    exit 1
fi
echo "✓ Redis is running"

echo ""
echo "Starting platform..."
python3 platform/ingest_tools/run_platform.py \
    --base-dir "$PROJECT_DIR" \
    --log-dir logs \
    --venv venv/bin/activate \
    --redis-port 6379
