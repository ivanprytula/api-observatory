# Documentation Changelog

Track structural and process changes to the docs so returning contributors can see what changed since their last session.

## 2026-08-11

- Collapsed `docs/02-architecture/infrastructure-architecture.md` into `docs/07-deployment/app-repo-contract.md`; the 23-line file added no new information.
- Replaced duplicated onboarding command blocks in `docs/personal/05-cross-functional-role-onboarding.md` with a link to the canonical checklist.
- Stripped duplicate evidence-status definitions from `docs/01-intro/application-lifecycle.md`; inline references now link to the README.
- Replaced the repository ownership table in `docs/01-intro/application-lifecycle.md` with a link to the README.
- Replaced the AWS MVP deployment narrative in `docs/05-development/onboarding-and-delivery-checklist.md §5` and `docs/01-intro/application-lifecycle.md §6` with one-paragraph summaries plus links.
- Replaced the duplicated project-purpose paragraph in `docs/01-intro/application-lifecycle.md` and `docs/03-planning/mvp-roadmap.md` with links to the README.
- Replaced the 6-step "Development Loop" numbered list in `docs/05-development/dev-workflows.md` with a link to the canonical checklist.
- Fixed broken doc references in `docs/personal/05-cross-functional-role-onboarding.md` (pillar guides, `00-project-overview.md`, Track labels) to point to current paths or the README.
- Updated `CLAUDE.md` to reference `docs/07-deployment/app-repo-contract.md` instead of the deleted `infrastructure-architecture.md`.
- Added glossary, developer journey diagram, and scope boundary to `README.md`.
- Added FAQ to `docs/04-setup/setup-guide.md`.

## 2026-08-11 (validation pass)

- Removed duplicate `## Development Loop` / `## Canonical local workflow` headers in `dev-workflows.md`; kept only `## Proof Selection`.
- Replaced full incident-lifecycle summary in `user-guide.md` with a one-line link to the operations guide.
- Removed architecture-only notes (Operations UI Direction, agent SSE stream) from `user-guide.md`; these belong in `decisions.md` and `application-architecture.md`.
- Condensed Manual Compose Watch subsection in `setup-guide.md` to a 3-line pointer to Docker docs; removed inline command blocks.
- Moved database client connection strings from `setup-guide.md` to service READMEs; replaced with a one-line pointer.
- Added "What You Don't Need" section to `setup-guide.md` to reduce onboarding friction.
- Tightened `application-lifecycle.md` opening from 5 sentences to 2.
- Fixed broken `infrastructure-architecture.md` path reference in `cross-functional-role-onboarding.md` to point to `decisions.md`.
- Fixed vague "Project Overview, Architecture Overview, and Roadmap" reference to link to actual docs.
- Created `docs/glossary.md` as the single source of truth for domain terms; replaced inline glossary in `README.md` with a link.

## 2026-08-11 (second validation pass)

- Tightened `application-lifecycle.md` opening: removed redundant second sentence that duplicated the first.
- Trimmed walkthroughs in `dev-workflows.md`: Junior (removed 5-line setup command block), Middle (removed `db-auto-init` code block), Senior (removed `.env` enable preamble). All now reference commands inline instead of repeating code blocks.
- Fixed "proof selection table below" to "above" reference in `dev-workflows.md` after duplicate header removal.
- Condensed HTTPS setup sequence in `setup-guide.md`: removed `curl` verification and `lab-ingress-smoke` from the main sequence.
- Deduplicated verification/troubleshooting in `setup-guide.md`: removed second `docker compose ps` / `docker compose logs` code block.
- Trimmed "Optional Local Capabilities" in `setup-guide.md`: removed redundant HTTPS and pgvector entries already covered elsewhere.
- Trimmed "Configuration Ownership" in `setup-guide.md`: removed inference/mcp config.py entries, database client strings, and local secrets paragraph.
- Updated "Containerized watch" table entry in `setup-guide.md` to match condensed subsection.
- Condensed `user-guide.md` Quick Start from 3 sentences to 1.
- Trimmed `user-guide.md` Practical Value: removed redundant SLA disclaimer already covered by the evidence note.
- Fixed duplicate "Application Architecture" link in `cross-functional-role-onboarding.md` Data Engineer section.
- Replaced 5-line evidence-status bullet list in `README.md` with one-line link to `docs/glossary.md`.
