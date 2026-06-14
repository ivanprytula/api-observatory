#!/usr/bin/env bash
set -euo pipefail

echo "==> Cleaning stopped testcontainers resources"
docker ps -a --filter "name=testcontainers" --format '{{.ID}}' | xargs -r docker rm -f

echo "==> Cleaning dangling testcontainers volumes"
docker volume ls --format '{{.Name}}' | grep 'testcontainers' | xargs -r docker volume rm

echo "Done. Next Postgres integration test run will auto-provision a fresh container."
