# AGENTS.md — Rules for AI Coding Agents

Global rules for how AI coding agents (Cline, Kilo, Copilot, etc.) should behave when working on this user's projects.

> **Project-specific overrides** for the current repo live in `.github/copilot-instructions.md` in that repo. Read that file too. The global rules here apply everywhere; project rules win on conflict.

---

## Brief overview

This file is deliberately lean. Three groups of rules live here:

1. **How to communicate** — priority, style, response shape, session mechanics.
2. **How to behave around files** — read scope, secrets, credential stores, `.gitignore`.
3. **Cross-project technical conventions** — short checklists and links; deep content lives in the project.

The repository's own `.github/instructions/` files carry the long-form examples. AGENTS.md carries the principles so an agent can act in any project, then points to the project files for depth.

---

## Priority

Optimize for low token usage. Be brief in chat. Prefer file edits and focused commands over long prose. Do not narrate internal reasoning, tool choice, or step-by-step plans unless asked. Do not paste large code blocks when the file can be edited directly. Do not restate the same fact twice. Do not dump large command output; summarize only the important lines.

## Read scope

Read this file first. Read only instruction files that match the files you touch. Do not read `.env`, secrets, or unrelated config unless explicitly asked. Do not scan `.venv`.

## Execution rules

Use tools immediately when the user asks to change files. Use `apply_patch` for manual edits. Use `uv run` for Python commands, tests, scripts, Alembic, Ruff, and Uvicorn. Do not commit, amend, or create branches unless explicitly asked. Do not revert user changes unless explicitly asked.

## Response style

Default shape: result, key validation, next step if needed. Keep explanations short and technical. Prefer prose over lists unless the content is inherently list-shaped. For simple tasks, one short paragraph is enough.

---

## Privacy and file access

### Respect `.gitignore`

Treat any path covered by `.gitignore`, `.dockerignore`, `.pre-commit-config.yaml` `exclude:` lists, or any other project ignore file as out of scope. Do not read, grep, or display the contents of ignored files unless the user explicitly names that specific file in that specific message. Typical ignored paths: `.venv/`, `.env`, `.env.*`, `node_modules/`, `_archive/`, `*.log`, build artifacts, `.copilot/`, `.kilo/`, `.cursor/`, `.aws/`, `.gcp/`, `.azure/`, `.ssh/`.

### Never read `~/.aws/*` (or any cloud credential store)

Never read `~/.aws/credentials`, `~/.aws/config`, `~/.aws/sso/`, `~/.aws/amazonq/`, or any file under `~/.aws/`. The same rule applies to other providers: `~/.gcp/`, `~/.azure/`, `~/.kube/config`, `~/.docker/config.json`, `~/.netrc`, `~/.boto`, `~/.config/gcloud/`, `~/.config/gh/hosts.yml`, `~/.ssh/id_*`, `~/.gnupg/`. When a hook, linter, or CI rule appears to come from a credential file, fix the *configuration* (`pre-commit-config.yaml`, exclude lists, env-var setup) — never the credential file itself. Treat placeholder values (`test`, `example`, `AKIAIOSFODNN7EXAMPLE`) the same as real values.

### Diagnostics without exposing secrets

For credential-related bugs, use only non-sensitive metadata: file existence (`ls -la`), file size, line count, env-var *names* (not values), or redacted output (`sed 's/=.*$/=***/'`). Never echo, log, or paste the value of an access key, secret key, session token, password, or API token. Refer to credential values only by their masked prefix (e.g. `test****`) as the hook itself does.

### When the user mentions a credentials issue

Do not try to reproduce by reading the credential file. Pivot to: (a) reading the hook's source/regex, (b) reading the *committed* file the hook flagged, (c) suggesting a non-invasive fix in the repo config. Config/credential files that are *committed* to the repo (e.g. `infra/terraform/**/*.tf`, sample `.env.example`) are fine to read; the rule applies to the user's private local credential store.

---

## Cross-project technical conventions

For each topic below, the principles are listed inline; the long-form guidance, examples, and code templates live in the project file linked at the end of the section. Read the project file before producing significant code in that area.

### Security (OWASP Top 10) → see `.github/instructions/security-and-owasp.instructions.md`

- **A01 / A10 — Access control & SSRF.** Deny by default. Validate every user-supplied URL with host/port/path allow-lists. Sanitize file paths against directory traversal.
- **A02 — Crypto.** Use Argon2 or bcrypt for passwords. Avoid MD5/SHA-1 for secrets. Default to HTTPS. Encrypt PII and tokens at rest. Never hardcode secrets.
- **A03 — Injection.** Parameterized SQL only. `shlex`-style escaping for OS args. `.textContent` over `.innerHTML` (or DOMPurify).
- **A05 / A06 — Misconfig & vulnerable deps.** Disable verbose errors in prod. Set CSP, HSTS, `X-Content-Type-Options`. Run `pip-audit` / `npm audit` after adding deps.
- **A07 — Auth.** Rotate session IDs on login. `HttpOnly; Secure; SameSite=Strict` cookies. Rate-limit login and password-reset.
- **A08 — Integrity.** Validate deserialized data. Prefer JSON over Pickle for untrusted sources.

### Markdown → see `.github/instructions/markdown.instructions.md`

Use H1 once for the document title. H2 for major sections, H3 for subsections; never skip a level. Use `` `code` `` inline, language-tagged triple backticks for blocks, `-` for unordered lists, `1.` for ordered. Link liberally to source files with line refs. Keep docs concrete.

**MD036 guardrail (always inline — every agent hits this).** Pre-commit `docs-quality-markdown` and markdownlint MD036 fail on emphasis-only headings. Never put a standalone `**...**` line that acts as a heading (e.g. `**Settings:**`, `**Notes:**`, `**Manual method:**`). Replace with real `###` / `####` headings or convert into paragraph text. Pre-flight: scan for `**...**` lines, convert each.

### Bash → see `.github/instructions/bash.instructions.md`

Shebang + metadata block. `set -o errexit -o pipefail -o nounset -o errtrace`. Trap ERR with a line-number reporter. Define `info`/`success`/`warn`/`error`/`require_command`/`command_exists` helpers at the top. Quote every variable (`"${var}"`). Use `${SCRIPT_DIR}` and `${PROJECT_ROOT}`; never hardcode paths. `trap cleanup EXIT` for teardown. Lint with `shellcheck`.

### SOLID principles → see `.github/instructions/solid-principles.instructions.md`

- **S** — Single Responsibility. One reason to change.
- **O** — Open/Closed. Extend, don't modify an `if-elif` chain.
- **L** — Liskov Substitution. No `NotImplementedError` from a method the parent promised; use composition.
- **I** — Interface Segregation. No fat interfaces; split into focused capability ABCs.
- **D** — Dependency Inversion. Depend on abstractions; inject via constructor or `Depends`. Bind in one factory.

### Design patterns → see `.github/instructions/design-patterns.instructions.md`

Diagnose the friction *before* picking a pattern. Pain-first decision tree: object-creation pain → creational; boundary pain → structural; changing-behavior pain → behavioral. Always ask: would a plain function, `dataclass`, or Pydantic model solve this with less code? If yes, do that.

### SSRF prevention (user-supplied URLs)

- **Scheme**: `https` only, or `http` only if an explicit config flag allows it.
- **Resolve the host** with DNS, then check the resolved IP against stdlib `ipaddress`.
- **Block private ranges**: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1`, link-local.
- Applies to webhook URLs, scraper targets, source-profile base URLs, and any other user-controlled URL.

### Secrets scanning → see `.github/hooks/secrets-scanner/README.md`

Every coding-agent session should end with a secrets scan over the diff. Pattern-based detection catches cloud keys, GitHub PATs, private-key blocks, connection strings, JWTs, internal-IP:port combos. Pair with auto-commit so a `block`-mode scanner stops the commit. Keep a per-project `SECRETS_ALLOWLIST` for test fixtures. Use `warn` in dev, `block` in CI.

### Anti-overengineering

Before suggesting any custom implementation, check whether stdlib or a well-known PyPI package solves the same problem. If one exists, recommend it (`hashlib`, `pydantic-settings`, `structlog`, `slowapi`, `prometheus-fastapi-instrumentator`, etc.). Flag abstractions with fewer than 3 callers. If a class has more than one reason to change, say so. If a file exceeds ~300 lines, flag it for splitting. Simplest solution wins — complexity must be justified by a concrete, current requirement, not a future hypothetical.

---

## Chat session reminders

- Start a new chat every 20 messages and whenever the topic changes, to keep context clean.
- At the 20th message, prepare a concise "Session Summary" (template below) and offer to paste it into a new chat.
- The first message of the new chat should be the summary, so context and continuity are preserved.

### Session Summary Template (copy/paste into new chat)

- **Session title:**
- **Date:**
- **Message count:**

- **Topics covered:**
   -

- **Key decisions:**
   -

- **Files changed / paths:**
   -

- **Commands / snippets to run:**
   -

- **Outstanding questions / next steps:**
   -

- **Brief context / notes:**
   -

(End of summary)
