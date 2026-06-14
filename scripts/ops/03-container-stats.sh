#!/bin/bash
# scripts/ops/03-container-stats.sh — Monitor container resource usage in real-time
# Usage: bash scripts/ops/03-container-stats.sh

set -e

echo "📊 Container Resource Usage (press Ctrl+C to stop)"
echo ""
echo "Format: CONTAINER_ID | NAME | CPU% | MEM USAGE / LIMIT | NET I/O"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker stats \
  --format "table {{.Container}}\t{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
  --no-trunc
