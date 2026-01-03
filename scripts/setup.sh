#!/bin/bash
# Setup script for Document Ingestion Platform

set -e  # Exit on error

echo "================================================"
echo "Document Ingestion Platform - Setup"
echo "================================================"

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_DIR"

echo ""
echo "1. Checking Python version..."
python3 --version || { echo "Error: Python 3 is required"; exit 1; }

echo ""
echo "2. Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

echo ""
echo "3. Activating virtual environment..."
source venv/bin/activate

echo ""
echo "4. Upgrading pip..."
pip install --upgrade pip

echo ""
echo "5. Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "6. Creating required directories..."
python3 config/config.py

echo ""
echo "7. Checking for .env file..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✓ Created .env from .env.example"
        echo "⚠️  IMPORTANT: Edit .env and add your MongoDB credentials!"
    else
        echo "⚠️  No .env.example found. You'll need to create .env manually."
    fi
else
    echo "✓ .env file already exists"
fi

echo ""
echo "8. Checking Redis..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        echo "✓ Redis is running"
    else
        echo "⚠️  Redis is installed but not running"
        echo "   Start it with: redis-server"
    fi
else
    echo "⚠️  Redis is not installed"
    echo "   Install it with:"
    echo "   - macOS: brew install redis"
    echo "   - Ubuntu: sudo apt-get install redis-server"
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your MongoDB credentials"
echo "2. Start Redis if not running: redis-server"
echo "3. Place PDF files in: data/master_library/"
echo "4. Run the platform: python3 platform/ingest_tools/run_platform.py"
echo ""
echo "To activate the virtual environment in the future:"
echo "  source venv/bin/activate"
echo ""
