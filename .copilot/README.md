# api-observatory — Project Copilot Context

This directory holds project-local Copilot and agent metadata.

## Purpose

Use `.copilot/` for project-specific AI state that should live close to the repo but stay separate from application code.

Typical contents:

- `project-config.yaml`: project-local Copilot configuration
- `README.md`: human-readable description of how the local AI metadata is organized
- `AGENT_COMMANDS.md`: reusable prompt/command fragments for this repo
- `memories/`: lightweight repo facts or working notes for future sessions

In practice, this directory helps keep Copilot behavior aligned with the current codebase instead of generic global defaults.

## Current Project Shape

This repository is now an async FastAPI monorepo centered on `services/ingestor`, with shared code in `libs/platform`, migrations in `alembic/`, tests in both `tests/` and `services/ingestor/tests/`, and additional service workspaces declared in `pyproject.toml`.

Primary stack:

| Layer | Choice |
| ----- | ------ |
| Language | Python 3.14 |
| Framework | FastAPI + Uvicorn |
| Database | PostgreSQL 17 |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Migrations | Alembic |
| Cache | Redis |
| Events | aiokafka |
| Packaging | uv + uv.lock |
| Linting | Ruff |
| Type checking | ty |
| Testing | pytest + pytest-asyncio + aiosqlite + testcontainers |

## Local AI Rules Worth Remembering

- Read `.github/copilot-instructions.md` first.
- Prefer local `.github/instructions/` files over global defaults when they exist.
- `libs/*` must not import from `services/*`.
- Alembic is the schema source of truth.
- Use `uv run` for Python tooling.
- Keep chat output terse and avoid dumping large command output.

## Files In This Directory

| File | Purpose |
| ---- | ------- |
| `.copilot/project-config.yaml` | Project-local config: stack, conventions, hooks, memories |
| `.copilot/README.md` | Overview of what this directory is for |
| `.copilot/AGENT_COMMANDS.md` | Reusable project-specific prompt fragments |
| `.copilot/memories/repo-context.md` | Short durable repo facts for future sessions |
