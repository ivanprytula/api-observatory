#!/usr/bin/env bash
set -euo pipefail
uvicorn services.ingestor.main:app --host 0.0.0.0 --port "${API_PORT:-8000}" --workers 1
