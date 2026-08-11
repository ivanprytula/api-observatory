# Glossary

Central definitions for terms used across the documentation. The README repeats the most
common ones inline; this file is the authoritative source for less frequent or ambiguous terms.

## Evidence Status

- **Core** — implemented and tested in the application path.
- **Lab** — executable/configurable in an isolated local environment, not claimed as production behavior.
- **Decision** — analyzed and configured but not exercised as production behavior.
- **Deferred** — waits for a measurable scale or ownership trigger.
- **Historical** — retained only to explain an older design.

## Deployment and Release

- **active_key** — a unique token on an open/acknowledged incident or contract baseline that prevents duplicate active rows for the same source.
- **aws-dev** — the current AWS MVP environment name; `aws-qa-stage` and `aws-prod` are future targets that must promote the same immutable digests.
- **expand/contract** — a migration sequencing pattern where a schema change is introduced in a backward-compatible way, consumed, then the old shape is removed in a later migration.
- **tree-SHA** — the immutable image tag `tree-<full-tree-SHA>` that binds a deployed image to an exact source commit and tree.
- **vertical slice** — a change that traces one user/behavior path through every affected layer: `migration → model → service → API → telemetry → docs`.

## Failure Behavior

- **fail-open** — a dependency failure policy where the system continues with degraded behavior (e.g., stale cache).
- **fail-closed** — a dependency failure policy where the system rejects the request until the dependency recovers.

## Architecture and Process

- **HITL** — human-in-the-loop; an agent workflow step that requires explicit operator approval before proceeding.
- **SSRF** — server-side request forgery; outbound requests to user-supplied URLs are validated against an allow-list.
- **CQRS** — command/query responsibility segregation; write-side and read-side paths are handled by separate code paths.
- **testcontainers** — a library that provisions disposable Docker containers during tests, used here for temporary PostgreSQL instances.
- **OIDC** — OpenID Connect; the GitHub-to-AWS authentication mechanism used for CI image publishing and deployment.
