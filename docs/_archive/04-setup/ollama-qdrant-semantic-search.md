# Ollama + Qdrant Semantic Search Setup for Kilo Code

Track: B — Engineering Execution

Infrastructure for **Kilo Code extension** to enable semantic search and long-term memory via MCP.

---

## Overview

This setup provides Kilo Code (VSCode extension) with:

- **Semantic code search**: Find relevant code by meaning across the codebase
- **Long-term memory**: Store and recall past conversations and decisions
- **Context-aware responses**: Retrieve related context for better answers

Kilo Code connects via MCP (Model Context Protocol) to access these capabilities.

---

## Prerequisites

- Docker and Docker Compose
- Kilo Code VSCode extension installed

---

## Quick Install

### Option A: Docker Compose (Recommended)

Add to `docker-compose.yml`:

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
    command: []

  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    # Pull model on first start
    # docker exec ollama ollama pull nomic-embed-text
```

Create volume:

```bash
mkdir -p ./qdrant_storage
docker volume create ollama_models
```

Start services:

```bash
docker compose up -d qdrant ollama
docker exec ollama ollama pull nomic-embed-text
```

### Option B: Stand-alone Containers

```bash
docker run -d --name qdrant -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant:latest
docker run -d --name ollama -p 11434:11434 -v ollama_models:/root/.ollama ollama/ollama:latest
docker exec ollama ollama pull nomic-embed-text
```

---

## MCP Configuration

Create or update `.kilo/mcp.json`:

```json
{
  "mcp": {
    "semantic-search": {
      "command": "uv",
      "args": ["run", "--with", "mcp[mypy]", "mcp-server-semantic"],
      "env": {
        "OLLAMA_URL": "http://127.0.0.1:11434",
        "QDRANT_URL": "http://127.0.0.1:6333"
      }
    }
  }
}
```

Or use STDIO transport with a custom MCP server script.

---

## Available MCP Tools

When configured, Kilo Code gains these tools:

| Tool | Purpose |
|------|---------|
| `semantic_search` | Search codebase by meaning |
| `store_memory` | Save conversation context |
| `recall_memory` | Retrieve past interactions |
| `index_code` | Add files to semantic index |

---

## Verification

```bash
# Check Qdrant
curl http://127.0.0.1:6333/health
# Expected: {"status":"ok"}

# Check Ollama
curl http://127.0.0.1:11434/api/tags
# Expected: {"models":[...]}
```

In Kilo Code VSCode extension:

- Open Chat panel → Tools tab
- Verify `semantic-search` server appears
- Test with: "Search for database connection patterns in this codebase"

---

## Resource Requirements

- **Ollama**: ~2GB RAM (CPU), ~4GB with GPU acceleration
- **Qdrant**: ~200MB RAM (scales with collection size)

Both services lightweight enough to run continuously on dev machines.

---

## Integration with Codebase

### Indexing Working Directory

Configure Kilo Code to index:

```json
{
  "indexing": {
    "include": ["services/**/*.py", "libs/**/*.py"],
    "exclude": ["tests/**", ".venv/**", "__pycache__/**"]
  }
}
```

---

## Stopping/Removing

```bash
docker stop ollama qdrant
docker rm ollama qdrant
rm -rf ./qdrant_storage
docker volume rm ollama_models  # Only if want to delete models
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection refused" | Ensure both services running: `docker ps` |
| Model not found | Pull embedding model: `docker exec ollama ollama pull nomic-embed-text` |
| No tools appear in Kilo Code | Check `.kilo/mcp.json` path and restart VSCode |
| Slow responses | Reduce model size or add CPU/GPU resources |
