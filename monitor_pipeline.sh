#!/bin/bash
# Monitoring and Debugging Script for Multi-Worker Pipeline

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================"
echo "Pipeline Monitoring Dashboard"
echo -e "======================================${NC}"
echo ""

# Function to check if Redis is running
check_redis() {
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis is running${NC}"
        return 0
    else
        echo -e "${RED}✗ Redis is not running${NC}"
        return 1
    fi
}

# Function to show queue depths
show_queues() {
    echo -e "\n${BLUE}Queue Depths:${NC}"
    echo "-------------"
    
    EXTRACTION_JOBS=$(redis-cli LLEN extraction_jobs 2>/dev/null || echo "0")
    CHUNKING_QUEUE=$(redis-cli LLEN document_processing_queue 2>/dev/null || echo "0")
    EMBEDDING_QUEUE=$(redis-cli LLEN embedding_queue 2>/dev/null || echo "0")
    
    echo -e "  Extraction Jobs:  ${YELLOW}$EXTRACTION_JOBS${NC}"
    echo -e "  Chunking Queue:   ${YELLOW}$CHUNKING_QUEUE${NC}"
    echo -e "  Embedding Queue:  ${YELLOW}$EMBEDDING_QUEUE${NC}"
}

# Function to show active workers
show_workers() {
    echo -e "\n${BLUE}Active Workers:${NC}"
    echo "---------------"
    
    MANAGER_COUNT=$(ps aux | grep "extraction_manager.py" | grep -v grep | wc -l | tr -d ' ')
    EXTRACTION_COUNT=$(ps aux | grep "extraction.py.*--worker-id" | grep -v grep | wc -l | tr -d ' ')
    CHUNKING_COUNT=$(ps aux | grep "chunking.py.*--worker-id" | grep -v grep | wc -l | tr -d ' ')
    EMBEDDING_COUNT=$(ps aux | grep "embedding.py.*--worker-id" | grep -v grep | wc -l | tr -d ' ')
    
    echo -e "  Extraction Manager: ${GREEN}$MANAGER_COUNT${NC}"
    echo -e "  Extraction Workers: ${GREEN}$EXTRACTION_COUNT${NC}"
    echo -e "  Chunking Workers:   ${GREEN}$CHUNKING_COUNT${NC}"
    echo -e "  Embedding Workers:  ${GREEN}$EMBEDDING_COUNT${NC}"
}

# Function to show recent errors
show_errors() {
    echo -e "\n${BLUE}Recent Errors (last 5):${NC}"
    echo "------------------------"
    
    if [ -d "logs" ]; then
        ERRORS=$(grep -h "ERROR\|event=.*_failed\|event=error" logs/*.log 2>/dev/null | tail -5)
        if [ -z "$ERRORS" ]; then
            echo -e "  ${GREEN}No recent errors${NC}"
        else
            echo "$ERRORS" | while IFS= read -r line; do
                echo -e "  ${RED}$line${NC}"
            done
        fi
    else
        echo -e "  ${YELLOW}No logs directory found${NC}"
    fi
}

# Function to show recent successes
show_successes() {
    echo -e "\n${BLUE}Recent Successes (last 3):${NC}"
    echo "--------------------------"
    
    if [ -d "logs" ]; then
        SUCCESSES=$(grep -h "event=job_completed.*status=success" logs/*.log 2>/dev/null | tail -3)
        if [ -z "$SUCCESSES" ]; then
            echo -e "  ${YELLOW}No completed jobs yet${NC}"
        else
            echo "$SUCCESSES" | while IFS= read -r line; do
                echo -e "  ${GREEN}$line${NC}"
            done
        fi
    else
        echo -e "  ${YELLOW}No logs directory found${NC}"
    fi
}

# Function to show trace IDs
show_trace_ids() {
    echo -e "\n${BLUE}Recent Trace IDs (last 5):${NC}"
    echo "--------------------------"
    
    if [ -d "logs" ]; then
        TRACES=$(grep -h "trace_id=" logs/extraction-manager*.log 2>/dev/null | grep "event=job_created" | tail -5 | grep -o "trace_id=[^ ]*" | cut -d= -f2)
        if [ -z "$TRACES" ]; then
            echo -e "  ${YELLOW}No trace IDs found${NC}"
        else
            echo "$TRACES" | while IFS= read -r trace; do
                echo -e "  ${BLUE}$trace${NC}"
            done
        fi
    else
        echo -e "  ${YELLOW}No logs directory found${NC}"
    fi
}

# Function to track a specific trace ID
track_trace() {
    if [ -z "$1" ]; then
        echo -e "${RED}Usage: $0 track <trace_id>${NC}"
        return 1
    fi
    
    TRACE_ID=$1
    echo -e "\n${BLUE}Tracking trace_id: $TRACE_ID${NC}"
    echo "================================="
    
    if [ -d "logs" ]; then
        grep -h "trace_id=$TRACE_ID" logs/*.log 2>/dev/null | while IFS= read -r line; do
            # Color code by stage
            if [[ $line == *"stage=extraction"* ]]; then
                echo -e "${YELLOW}[EXTRACT]${NC} $line"
            elif [[ $line == *"stage=chunking"* ]]; then
                echo -e "${BLUE}[CHUNK]${NC} $line"
            elif [[ $line == *"stage=embedding"* ]]; then
                echo -e "${GREEN}[EMBED]${NC} $line"
            else
                echo "$line"
            fi
        done
    else
        echo -e "${RED}No logs directory found${NC}"
    fi
}

# Main menu
case "$1" in
    "track")
        track_trace "$2"
        ;;
    "watch")
        # Continuous monitoring
        while true; do
            clear
            check_redis
            show_workers
            show_queues
            show_successes
            show_errors
            echo ""
            echo -e "${YELLOW}Refreshing in 5 seconds... (Ctrl+C to stop)${NC}"
            sleep 5
        done
        ;;
    *)
        # One-time dashboard
        check_redis
        show_workers
        show_queues
        show_trace_ids
        show_successes
        show_errors
        
        echo ""
        echo -e "${BLUE}Commands:${NC}"
        echo "  $0              - Show this dashboard"
        echo "  $0 watch        - Continuous monitoring (refreshes every 5s)"
        echo "  $0 track <id>   - Track a specific trace_id through pipeline"
        echo ""
        echo -e "${BLUE}Useful Manual Commands:${NC}"
        echo "  tail -f logs/pipeline_main_*.log    - Watch main orchestrator"
        echo "  redis-cli KEYS 'lock:*'             - Show active file locks"
        echo "  redis-cli LRANGE extraction_jobs 0 -1 - Show all extraction jobs"
        echo "  grep 'event=error' logs/*.log       - Find all errors"
        ;;
esac
