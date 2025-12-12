#!/bin/bash
# Retry script for building context files that failed due to server issues
# Usage: ./retry_build.sh [graph_id] [max_retries] [delay_seconds]

set -e

# Default values
MAX_RETRIES=${2:-5}
DELAY=${3:-30}
GRAPHS_TO_BUILD=("biobricks-toxcast" "biohealth")

# If graph_id is provided, only build that one
if [ -n "$1" ]; then
    GRAPHS_TO_BUILD=("$1")
fi

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "=========================================="
echo "Retry Build Script"
echo "=========================================="
echo "Max retries: $MAX_RETRIES"
echo "Delay between retries: ${DELAY}s"
echo "Graphs to build: ${GRAPHS_TO_BUILD[*]}"
echo "=========================================="
echo ""

# Function to build a graph with retries
build_with_retry() {
    local graph_id=$1
    local attempt=1
    local success=false
    
    while [ $attempt -le $MAX_RETRIES ]; do
        echo "[Attempt $attempt/$MAX_RETRIES] Building $graph_id..."
        
        if python -m omnigraph_agent.context_builder.cli build "$graph_id" 2>&1; then
            echo "✓ Successfully built $graph_id"
            success=true
            break
        else
            local exit_code=$?
            echo "✗ Build failed for $graph_id (exit code: $exit_code)"
            
            if [ $attempt -lt $MAX_RETRIES ]; then
                echo "Waiting ${DELAY}s before retry..."
                sleep $DELAY
            fi
        fi
        
        attempt=$((attempt + 1))
    done
    
    if [ "$success" = false ]; then
        echo "✗ Failed to build $graph_id after $MAX_RETRIES attempts"
        return 1
    fi
    
    return 0
}

# Build each graph
failed_graphs=()
for graph_id in "${GRAPHS_TO_BUILD[@]}"; do
    echo ""
    echo "----------------------------------------"
    echo "Building: $graph_id"
    echo "----------------------------------------"
    
    if ! build_with_retry "$graph_id"; then
        failed_graphs+=("$graph_id")
    fi
    
    echo ""
done

# Summary
echo "=========================================="
echo "Build Summary"
echo "=========================================="

if [ ${#failed_graphs[@]} -eq 0 ]; then
    echo "✓ All graphs built successfully!"
    exit 0
else
    echo "✗ Failed graphs: ${failed_graphs[*]}"
    echo ""
    echo "These graphs may need manual retry or the endpoints may be down."
    exit 1
fi
