# Plan Maintenance

Operational procedures for keeping project artifacts current after changes.

## Adding a service

Update `docs/07-deployment/app-repo-contract.md`, add per-service test + observability rows to `docs/02-architecture/baseline-checklist.md`, and add a container node + Router/Feature Map row to `docs/02-architecture/application-architecture.md`.

## Adding a dependency

No new tooling needed; existing `pip-audit`, Dependabot, and Trivy controls apply. Justify per the evolution-playbook dependency-lifecycle checklist.

## Advancing a roadmap phase

Update `docs/03-planning/mvp-roadmap.md` and add a changelog line; flip the affected row's Status in `docs/02-architecture/application-architecture.md` if a deferred feature became active.

## Changing infra topology

Update `docs/07-deployment/app-repo-contract.md` and, if ownership moved, the sibling infra repo's `docs/.plans/repo-split-app-infra.md` ownership table, in the same change.

## Yearly (June)

Run the OWASP review in `docs/02-architecture/security-architecture.md`; file gaps as issues.
