# AGENTS.md — Rules for AI Coding Agents

Global rules for AI coding agents (Cline, Kilo, Copilot, etc.) working in this repository.

## Priority

Optimize for low token usage. Be brief in chat. Prefer file edits and focused commands over long prose. Do not narrate internal reasoning, tool choice, or step-by-step plans unless asked. Do not paste large code blocks when the file can be edited directly. Do not restate the same fact twice. Summarize important lines only.

## Read scope

Read this file first. Read only instruction files that match the files you touch. Do not read `.env`, secrets, or unrelated config unless explicitly asked. Do not scan `.venv`.

## Execution rules

Use tools immediately when the user asks to change files. Use `apply_patch` for manual edits. Use `uv run` for Python commands, tests, scripts, Alembic, Ruff, and Uvicorn. After refactoring — especially when changing test files or touching more than one module — run all code-quality pre-commit hooks (Ruff, docs, checker, Bandit, type checking, etc.) before running unit/integration/e2e tests. After testing, remove unneeded test artifacts; inspect targets first and never remove user or persistent data without explicit approval. Do not commit, amend, or create branches unless explicitly asked. Do not revert user changes unless explicitly asked.

**Validate Python edits immediately.** After editing any `.py` file, run `python -m py_compile <file>` or `ruff check <file>` on that file before moving on. Do not batch edits across many files and validate only at the end. Catch syntax/indentation errors per file, then continue.

## Mode gating

At the start of each turn, check the current execution mode (ask, code, plan, etc.) before performing file operations. In ask/read-only modes, only read files; never write, edit, or execute side-effecting commands. File writes and edits are permitted only in code/plan modes.

## Patterns & Gotchas

- `docker compose up` with `--pull` followed immediately by service names breaks because `--pull` takes an optional argument (`always`/`missing`/`never`). Always use `--pull=always` or place `--wait` before `--pull` so service names aren't consumed as the pull mode.

## Response style

Default shape: result, key validation, next step if needed. Keep explanations short and technical. Prefer prose over lists unless the content is inherently list-shaped. For simple tasks, one short paragraph is enough.

## Working preferences

- Prefer small, reviewable patches over broad refactors.
- Offer one recommended approach; mention alternatives only when tradeoffs are material.
- Preserve backward compatibility unless the user explicitly authorizes a breaking change.
- Keep runtime dependencies minimal and explain why each new dependency is needed.
- When a product decision is ambiguous, present concrete options and wait for direction.
- Favor operationally simple solutions with explicit failure modes and useful observability.

## Git operations

Never use `git add .` or `git add -A`. When staging for commit, explicitly list only the files relevant to the current task. If the task scope is unclear, ask before staging. Never drop git stashes in any repository; preserve them across sessions. **Never git push code unless explicitly given such a task.**

## Commit messages

Write a short headline using the conventional commits framework (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, etc.). Optionally add a commit body that explains why the change was made and the motivation, but do not list the files changed — that is already visible in `git diff`.

## Privacy and file access

### Respect `.gitignore`

Treat `.gitignore`, `.dockerignore`, `.pre-commit-config.yaml` `exclude:` lists, or any project ignore file as out of scope. Do not read ignored files unless the user explicitly names that specific file. Typical ignored paths: `.venv/`, `.env`, `.env.*`, `node_modules/`, `_archive/`, `*.log`, build artifacts, `.copilot/`, `.kilo/`, `.cursor/`, `.aws/`, `.gcp/`, `.azure/`, `.ssh/`.

### Never read secrets or credential stores

Never read `.env`, `.env.*`, `secrets/`, `credentials`, or any file with secrets, API keys, passwords, or tokens — even if committed (`.env.example` fixtures are fine). Ask the user to share only the relevant masked value. This overrides read-scope allowance.

Never read `~/.aws/`, `~/.gcp/`, `~/.azure/`, `~/.kube/config`, `~/.docker/config.json`, `~/.netrc`, `~/.boto`, `~/.config/gcloud/`, `~/.config/gh/hosts.yml`, `~/.ssh/id_*`, `~/.gnupg/`. When a hook appears to come from a credential file, fix the *configuration*, never the credential file itself. Treat placeholder values (`test`, `example`, `AKIAIOSFODNN7EXAMPLE`) as real values.

### Diagnostics without exposing secrets

For credential bugs, use only non-sensitive metadata: file existence, size, line count, env-var *names* (not values), or redacted output. Never echo, log, or paste actual credential values. Refer to values by masked prefix only.

### When the user mentions a credentials issue

Do not reproduce by reading the credential file. Pivot to: (a) the hook's source/regex, (b) the committed file the hook flagged, (c) a non-invasive fix in repo config. Committed config/credential files (e.g. `infra/terraform/**/*.tf`, `.env.example`) are fine to read.

## Cross-project technical conventions

For each topic below, the principles are listed inline; long-form guidance lives in the linked project file. Read it before producing significant code in that area.

### Security (OWASP Top 10) → `../agent-forge/instructions/security-and-owasp.instructions.md`

Deny by default. Validate user-supplied input. Use parameterized queries. Encrypt PII at rest. Never hardcode secrets. Validate deserialized data. Default to HTTPS. Set security headers. Rate-limit auth endpoints.

### Markdown → `../agent-forge/instructions/markdown.instructions.md`

Use H1 once, H2 for major sections, H3 for subsections. Never use emphasis-only headings (MD036).

### Bash → `../agent-forge/instructions/bash.instructions.md`

Use strict mode, quote variables, lint with shellcheck.

### Design principles → `CLAUDE.md` (ACROSS) + `../agent-forge/instructions/solid-principles.instructions.md`

Use ACROSS as the primary design lens. SOLID as secondary. Prefer composition and pragmatic interfaces over rigid purity.

### Design patterns → `../agent-forge/instructions/design-patterns.instructions.md`

Diagnose friction before picking a pattern. Prefer plain functions, dataclasses, or models over patterns when they solve the problem with less code.

### SSRF prevention → `../agent-forge/instructions/security-and-owasp.instructions.md`

Validate scheme, resolve host, check resolved IP against private ranges for all user-supplied URLs.

### Secrets scanning → `.pre-commit-config.yaml`

Use the pinned Gitleaks hook. Keep false-positive exceptions narrow.

### Anti-overengineering

Prefer stdlib or well-known packages. Flag abstractions with fewer than 3 callers. Flag files exceeding ~300 lines. Simplest solution wins.

## Progressive-loading routes

Read the relevant instruction file before producing significant code in that area:

- **Python** → `../agent-forge/instructions/python.instructions.md` + `pydantic.instructions.md`
- **FastAPI** → `../agent-forge/instructions/fastapi.instructions.md` + `fastapi-testing.instructions.md`
- **SQL** → `../agent-forge/instructions/sql.instructions.md`
- **Testing** → `../agent-forge/instructions/tests.instructions.md`
- **Docker** → `../agent-forge/instructions/containerization-docker-best-practices.instructions.md`
- **Bash** → `../agent-forge/instructions/bash.instructions.md`
- **Security** → `../agent-forge/instructions/security-and-owasp.instructions.md`
- **Design/architecture** → `../agent-forge/instructions/design-patterns.instructions.md` + `solid-principles.instructions.md`
- **Async** → `../agent-forge/instructions/async-patterns.instructions.md`
- **project architecture** → `docs/PROJECT_CONTEXT.md` + `docs/02-architecture/engineering-topics.md`

## Instruction sync rule

Whenever you add or update an instruction file listed in **Progressive-loading routes**, check whether the sibling infra repository has the same instruction file. If it does, update both repos to keep them in sync. If the sibling repo does not have it, update only the repo you were asked to modify.

## Central agent standards

Shared agent standards are maintained in `agent-forge`:

- Git workflow → `../agent-forge/instructions/git-workflow.instructions.md`
- Repo standards → `../agent-forge/skills/repo-standards/SKILL.md`
