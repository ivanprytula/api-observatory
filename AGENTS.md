# AGENTS.md — Rules for AI Coding Agents

Global rules for agents working in this repository. Generic behavior rules live in `../agent-forge/instructions/agent-behavior.instructions.md`.

## Patterns & Gotchas

- `docker compose up` with `--pull` followed immediately by service names breaks because `--pull` takes an optional argument (`always`/`missing`/`never`). Always use `--pull=always` or place `--wait` before `--pull` so service names aren't consumed as the pull mode.

## Docker cleanup

After test builds or smoke tests with running containers, clean up Docker resources:

- Stop services: `docker compose down`
- Prune stopped containers: `docker container prune -f`
- Prune unused images: `docker image prune -f`
- Prune unused volumes: `docker volume prune -f`
- Prune unused networks: `docker network prune -f`

## Progressive-loading routes

Read the relevant skill file before producing significant code in that area:

- **Python** → `../agent-forge/instructions/python.instructions.md` + `pydantic.instructions.md`
- **FastAPI** → `../agent-forge/skills/fastapi-testing/SKILL.md` + `fastapi.instructions.md`
- **SQL** → `../agent-forge/instructions/sql.instructions.md`
- **Testing** → `../agent-forge/instructions/tests.instructions.md`
- **Docker** → `../agent-forge/instructions/containerization-docker-best-practices.instructions.md`
- **Bash** → `../agent-forge/instructions/bash.instructions.md`
- **Security** → `../agent-forge/instructions/security-and-owasp.instructions.md`
- **Design/architecture** → `../agent-forge/instructions/design-patterns.instructions.md` + `../agent-forge/instructions/solid-principles.instructions.md`
- **Async** → `../agent-forge/instructions/async-patterns.instructions.md`
- **project architecture** → `docs/PROJECT_CONTEXT.md` + `docs/02-architecture/engineering-topics.md`

## Instruction sync rule

Whenever you add or update an instruction file listed in **Progressive-loading routes**, check whether the sibling infra repository has the same instruction file. If it does, update both repos to keep them in sync. If the sibling repo does not have it, update only the repo you were asked to modify.

## Central agent standards

Shared agent standards are maintained in `agent-forge`:

- Git workflow → `../agent-forge/instructions/git-workflow.instructions.md`
- Repo standards → `../agent-forge/instructions/agent-behavior.instructions.md`

## CLI vs MCP boundary

Prefer mature CLIs (`docker compose`, `just`, `uv`, `alembic`, `psql`) for infrastructure and one-off commands. Use MCP only for stateful, permission-aware access to the observatory API.

## Python execution

For running Python modules, scripts, and tests in the shell, use `uv run ...`, not `python -c ...` or `python3 -c ...`.

## Skill discovery

For a lightweight catalog of all available skills, see `../agent-forge/skills/manifest.json` or `../agent-forge/skills/index.md`. Load the full `SKILL.md` only when the task matches the skill's trigger.

## Skill-not-found fallback

If no skill trigger matches, search `../agent-forge/skills/manifest.json` by keyword or escalate to the `self-improving-agent` instructions at `../agent-forge/instructions/self-improving-agent.instructions.md`.
