# Prompting Checklist

Track: C — Architecture and Platform Strategy

A short, copy-paste checklist and template to keep prompts small and actionable.

## Checklist

- Goal: start with a single-line goal and one measurable success criterion.
- Repro: include the exact command to run and only the failing output lines (last ~8 lines).
- Files: point to exact file paths and line ranges to inspect (e.g. .github/workflows/ci.yml#L120-L180).
- Action: ask for one precise action (e.g. "fix and apply patch to file X").
- Snippets: prefer diffs or 20–40 lines around the problem instead of entire files.
- Searches: when you want a scan, ask for a search (e.g. "search for '127.0.0.1' under .github/** and return matches").
- Secrets: never paste secrets — use placeholders (SECRET_VALUE) or ask me to read local files.
- Multi-file work: break into steps and request "process files one-by-one; stop after each file for review."

## Use the "no auto-read" prefix

If you do not want me to fetch files from the repo, prefix your request with `no auto-read` and paste only the minimal snippets you want me to use.

## Quick template (copy & paste)

Goal: Fix [one-line description]. Success: [exact criterion].

Repro (command + failing lines):

```bash
uv run pytest tests/integration/test_scheduler.py -k test_x -q
# paste only the last ~8 failing lines here
```

Files to read: .github/workflows/ci.yml L120-L180; services/processor/main.py L10-L40

Do this: Edit `services/processor/main.py` to replace X with Y and stop; do not read other files.

Constraints: no full test runs, do not expose secrets, process files one-by-one.

---

## Use this tiny checklist and template when you click “Add selection to Chat.”

Checklist

- Goal: one-line objective + measurable success criteria.
- Selection: paste file header (path + Lstart-Lend) and the selected lines (prefer 10–40 lines; 20 is a good sweet spot).
- Tracebacks: paste the full stack trace or at least the last ~20 lines.
- Repro: exact command you ran (with flags) and environment note (OS, Python, uv version).
- Files: include at most 2–3 supporting files; for more, break into steps.
- Secrets: never paste them — replace with PLACEHOLDER.
- Action: ask one specific thing (explain, fix, produce patch for file:X).
- Control reads: prefix with no auto-read if you don’t want me fetching repo files.

```text
no auto-read   # optional: prevents automatic repo reads

Goal: <one-line goal>. Success: <what “done” looks like>.

Selection:
File: services/processor/main.py L120-L140
<PASTE THE SELECTED LINES HERE (10–40 lines)>

Traceback (if any):
<PASTE last ~20 lines of the error/stack trace>

Repro (exact command):
uv run pytest tests/integration/test_scheduler.py -k test_x -q

Files to include (optional, max 3): .github/workflows/ci.yml L720-L730; services/processor/__init__.py L1-L20

Do this (single action): Fix `services/processor/main.py` lines 125-128 to handle None return from `get_cache()` and return a minimal patch; stop after editing that file.

Constraints: no full test runs; do not expose secrets; process files one-by-one.
```

If you want, start your prompt with `no auto-read` and I will only use the snippets you paste.
