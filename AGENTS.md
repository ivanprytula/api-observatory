# AGENTS.md — Rules for AI Coding Agents

Global rules for AI coding agents (Cline, Kilo, Copilot, etc.) working in this repository. Project-specific overrides live in `.github/copilot-instructions.md`.

## Priority

Optimize for low token usage. Be brief in chat. Prefer file edits and focused commands over long prose. Do not narrate internal reasoning, tool choice, or step-by-step plans unless asked. Do not paste large code blocks when the file can be edited directly. Do not restate the same fact twice. Summarize important lines only.

## Read scope

Read this file first. Read only instruction files that match the files you touch. Do not read `.env`, secrets, or unrelated config unless explicitly asked. Do not scan `.venv`.

## Execution rules

Use tools immediately when the user asks to change files. Use `apply_patch` for manual edits. Use `uv run` for Python commands, tests, scripts, Alembic, Ruff, and Uvicorn. After refactoring — especially when changing test files or touching more than one module — run all code-quality pre-commit hooks (Ruff, docs, checker, Bandit, type checking, etc.) before running unit/integration/e2e tests. After testing, remove unneeded test artifacts; inspect targets first and never remove user or persistent data without explicit approval. Do not commit, amend, or create branches unless explicitly asked. Do not revert user changes unless explicitly asked.

**Validate Python edits immediately.** After editing any `.py` file, run `python -m py_compile <file>` or `ruff check <file>` on that file before moving on. Do not batch edits across many files and validate only at the end. Catch syntax/indentation errors per file, then continue.

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

Never use `git add .` or `git add -A`. When staging for commit, explicitly list only the files relevant to the current task. If the task scope is unclear, ask before staging. Never drop git stashes in any repository; preserve them across sessions.

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

For security-sensitive changes:
  read `../agent-forge/instructions/security-and-owasp.instructions.md`

For Bash scripts:
  read `../agent-forge/instructions/bash.instructions.md`

For Markdown documentation:
  read `../agent-forge/instructions/markdown.instructions.md`

For Python code:
  read `../agent-forge/instructions/python.instructions.md`
  read `../agent-forge/instructions/pydantic.instructions.md`

For FastAPI:
  read `../agent-forge/instructions/fastapi.instructions.md`
  read `../agent-forge/instructions/fastapi-testing.instructions.md`

For database/SQL:
  read `../agent-forge/instructions/sql.instructions.md`

For testing:
  read `../agent-forge/instructions/tests.instructions.md`

For Docker/containers:
  read `../agent-forge/instructions/containerization-docker-best-practices.instructions.md`

For infrastructure-as-code:
  read `../agent-forge/instructions/terraform.instructions.md`
  read `../agent-forge/instructions/ansible.instructions.md`

For Kubernetes:
  read `../agent-forge/instructions/kubernetes-deployment-best-practices.instructions.md`

For design/architecture decisions:
  read `../agent-forge/instructions/design-patterns.instructions.md`
  read `../agent-forge/instructions/solid-principles.instructions.md`

For GitHub Actions workflow changes:
  read `../agent-forge/instructions/yaml.instructions.md`
  read `../agent-forge/instructions/github-actions-ci-cd-best-practices.instructions.md`

For API/docs:
  read `../agent-forge/instructions/api-docs.instructions.md`

For async/concurrency:
  read `../agent-forge/instructions/async-patterns.instructions.md`

For performance:
  read `../agent-forge/instructions/performance-optimization.instructions.md`

For models/CRUD:
  read `../agent-forge/instructions/models.instructions.md`
  read `../agent-forge/instructions/crud.instructions.md`

For TOML:
  read `../agent-forge/instructions/toml.instructions.md`

For HTML/CSS:
  read `../agent-forge/instructions/html-css.instructions.md`

For LangChain:
  read `../agent-forge/instructions/langchain-python.instructions.md`

For project architecture, product decisions, or engineering topic lookups:
  read `docs/PROJECT_CONTEXT.md`
  read `docs/02-architecture/engineering-topics.md`

## Instruction sync rule

Whenever you add or update an instruction file listed in **Progressive-loading routes**, check whether the sibling infra repository has the same instruction file. If it does, update both repos to keep them in sync. If the sibling repo does not have it, update only the repo you were asked to modify, or the repo relevant to the specific action/question.

## Central agent standards

Shared agent standards are maintained in `agent-forge`:

- Git workflow → `../agent-forge/instructions/git-workflow.instructions.md`
- Repo standards (privacy, read scope, response style) → `../agent-forge/skills/repo-standards/SKILL.md`

---

## Skills

This repo includes reusable skills in agent-specific hidden directories (`.claude/skills/`, `.kilo/skills/`, etc.). Skills are agent playbooks — structured instructions for repeatable workflows.

| Skill                                                        | Purpose                                                     | Trigger                                                     |
| ------------------------------------------------------------ | ----------------------------------------------------------- | ----------------------------------------------------------- |
| [self-improving-agent](.claude/skills/self-improving-agent/SKILL.md) | Improve this AGENTS.md, create new skills, encode learnings | After completing a task, or when noticing repeated friction |

### Using Skills

- Read the skill's `SKILL.md` when the trigger condition is met.
- Follow the steps exactly as written.
- If a skill's instructions are stale or wrong, update the skill.

### Creating New Skills

When a workflow repeats — especially across projects — promote it to a skill. Use the `self-improving-agent` skill for guidance on when and how.

---

## Self-Correction Protocol

> This section defines how this file stays alive and accurate.

1. **Stale map?** If you discover that the Codebase Map above doesn't match reality, **update it now** before continuing your task. Don't leave it for later.

2. **User correction?** If a human corrects your behavior (e.g., "don't use that API", "run tests this way"), add the correction to the appropriate section of this file (Local Norms, Guardrails, or Patterns & Gotchas) so future sessions inherit it.

3. **Repeated friction?** If you notice yourself doing the same multi-step workflow more than once, consider creating a new skill in the appropriate agent skills directory. Use the [self-improving-agent skill](.claude/skills/self-improving-agent/SKILL.md) for the procedure.

4. **Post-task reflection.** After completing a significant task, briefly review:
   - Did anything surprise you?
   - Did you take a path that could be shortcutted next time?
   - If yes, record the insight in this file or as a new skill.

5. **Promotion rule.** Before promoting a learning to this file, check `.learnings/LEARNINGS.md` for related entries. If a pattern has `Recurrence-Count >= 3`, has been seen across at least 2 distinct tasks, and occurred within a 30-day window, it qualifies for promotion. Write the promoted rule as a short prevention rule, not a long incident write-up.

---

## Template Usage

This repository is designed as a centralized skills and instructions repo for the `api-obs-stack` workspace. When integrating it into a project:

1. From the target project root, run the appropriate adapter:

   ```bash
   bash ../agent-forge/adapters/kilo/apply.sh
   ```

2. Update the **Codebase Map** to reflect the project's actual structure.
3. Update **Local Norms** with the project's build commands, test commands, and conventions.
4. Delete placeholder entries (the italicized examples) and replace with real ones.
5. Keep the **Self-Correction Protocol** and **Guardrails** — they apply universally.
6. Add project-specific skills to the appropriate agent skills directory as your workflows emerge.

## Notes

- Project-specific configs (MCP servers, plugin configs, local overrides, runtime state) stay in each project.
- `.github/` CI/CD workflows stay project-local.
- `.learnings/` is gitignored by default to keep developer logs local. Enable team-wide sharing by removing the `.gitignore` entry.
