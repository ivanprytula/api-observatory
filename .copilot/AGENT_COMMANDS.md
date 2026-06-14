# Daily AI Agent Commands

Reusable prompt fragments for this repository.

## Session Start

```text
Audit this workspace for stale AI config in .copilot/ and .github/, summarize the last implemented slice, and list the top 3 next actions based on current repo state.
```

## Focused Review

```text
Review [file or diff] for async bugs, security issues, boundary violations, migration risk, and missing tests. Keep findings first.
```

## Auth Slice

```text
Review the auth/security slice around [file]. Focus on JWT/session handling, tenant scoping, API key scope checks, and deny-by-default behavior.
```

## Migration Safety

```text
Check this Alembic migration for safe upgrade/downgrade behavior, online migration risk, and unrelated autogenerate noise. Suggest the smallest cleanup.
```

## Repo Sync

```text
Compare .copilot/ and .github/ guidance with the current repo structure. Update stale project-local AI files to match the codebase without adding generic filler.
```

## Performance Pass

```text
Invoke autoresearch.
Goal: improve [metric] in [component].
Constraint: keep public behavior unchanged and preserve existing tests.
```

## Database Review

```text
Invoke postgresql-code-review on [model/migration/query file]. Focus on indexes, async access patterns, tenant scoping, and rollback safety.
```

## Architecture Pass

```text
Invoke architecture-blueprint-generator for the current monorepo state and summarize the service boundaries, shared libraries, migrations, and operational surfaces.
```

## End-of-Day Wrap-Up

```text
Summarize what changed today, what was validated, what remains in progress, and any repo-level decisions that should be preserved in .copilot/memories/repo-context.md.
```

## Useful One-Liners

| Goal | Prompt |
| ---- | ------ |
| Explain a migration risk | `Explain why this migration is risky to downgrade and what the safer downgrade strategy is.` |
| Review a security sub-step | `Review this security slice for correctness, regressions, and missing tests before I move to the next sub-step.` |
| Check service boundary | `Check whether this change violates the libs/* -> services/* boundary anywhere in the touched code.` |
| Tight validation | `Run the smallest test/lint commands that can falsify this change before widening scope.` |
| Update repo memory | `Write a short durable repo-context note for the changes we just validated.` |
