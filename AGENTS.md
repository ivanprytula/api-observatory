# AGENTS.md — Rules for AI Coding Agents

Global rules for agents working in this repository. Generic behavior rules live in `../agent-forge/instructions/agent-behavior.instructions.md`.

## Patterns & Gotchas

- `docker compose up` with `--pull` followed immediately by service names breaks because `--pull` takes an optional argument (`always`/`missing`/`never`). Always use `--pull=always` or place `--wait` before `--pull` so service names aren't consumed as the pull mode.

## Progressive-loading routes

Read the relevant skill file before producing significant code in that area:

- **Python** → `../agent-forge/skills/python/SKILL.md` + `pydantic.instructions.md`
- **FastAPI** → `../agent-forge/skills/fastapi-testing/SKILL.md` + `fastapi.instructions.md`
- **SQL** → `../agent-forge/skills/sql/SKILL.md`
- **Testing** → `../agent-forge/skills/pytest-coverage/SKILL.md`
- **Docker** → `../agent-forge/skills/docker/SKILL.md`
- **Bash** → `../agent-forge/skills/bash/SKILL.md`
- **Security** → `../agent-forge/skills/security-and-owasp/SKILL.md`
- **Design/architecture** → `../agent-forge/skills/design-patterns/SKILL.md` + `solid-principles/SKILL.md`
- **Async** → `../agent-forge/skills/async-patterns/SKILL.md`
- **project architecture** → `docs/PROJECT_CONTEXT.md` + `docs/02-architecture/engineering-topics.md`

## Instruction sync rule

Whenever you add or update an instruction file listed in **Progressive-loading routes**, check whether the sibling infra repository has the same instruction file. If it does, update both repos to keep them in sync. If the sibling repo does not have it, update only the repo you were asked to modify.

## Central agent standards

Shared agent standards are maintained in `agent-forge`:

- Git workflow → `../agent-forge/instructions/git-workflow.instructions.md`
- Repo standards → `../agent-forge/skills/repo-standards/SKILL.md`

## CLI vs MCP boundary

Prefer mature CLIs (`docker compose`, `just`, `uv`, `alembic`, `psql`) for infrastructure and one-off commands. Use MCP only for stateful, permission-aware access to the observatory API.

## Skill discovery

For a lightweight catalog of all available skills, see `../agent-forge/skills/manifest.json` or `../agent-forge/skills/index.md`. Load the full `SKILL.md` only when the task matches the skill's trigger.

## Skill-not-found fallback

If no skill trigger matches, search `../agent-forge/skills/manifest.json` by keyword or escalate to the `self-improving-agent` skill at `../agent-forge/skills/self-improving-agent/SKILL.md`.
