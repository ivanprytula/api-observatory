#!/usr/bin/env bash
# Entry point that starts both FastAPI and Streamlit
# For the ingestor container - runs both services on ports 8000 and 8501

set -euo pipefail

# Configuration
API_PORT="${API_PORT:-8000}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
INGESTOR_URL="${INGESTOR_URL:-http://127.0.0.1:${API_PORT}}"

echo "Starting API on port ${API_PORT} and Streamlit on port ${STREAMLIT_PORT}"
echo "Streamlit will connect to ingestor at: ${INGESTOR_URL}"

# Export INGESTOR_URL for Streamlit process
export INGESTOR_URL

# Start uvicorn in background
uvicorn services.ingestor.main:app --host 0.0.0.0 --port "${API_PORT}" --workers 1 &
UVICORN_PID=$!

# Wait for API to be ready before starting Streamlit
echo "Waiting for API to be ready..."
for i in {1..30}; do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${API_PORT}/health', timeout=3)" 2>/dev/null; then
        echo "API ready"
        break
    fi
    sleep 1
done

# Start Streamlit in background too
streamlit run streamlit_app.py \
    --server.port "${STREAMLIT_PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false &
STREAMLIT_PID=$!

echo "Both services started. uvicorn PID: ${UVICORN_PID}, streamlit PID: ${STREAMLIT_PID}"

# Wait for either process to exit (handles container termination)
wait -n

# If we get here, one service exited - kill the other
echo "One service exited, shutting down..."
kill "${UVICORN_PID}" 2>/dev/null || true
kill "${STREAMLIT_PID}" 2>/dev/null || true
exit 1
