---
name: Job-Ready SDLC Roadmap
overview: Focus the next 8-10 weeks on a production-like SDLC loop around the ingestor service first, then add one microservice incrementally. Prioritize high signal skills for hiring (CI/CD, cloud deployment, observability, resilience, async/perf) over enterprise-only overhead.
todos:
  - id: stabilize-ci-reliability
    content: Finalize fixture boundary model and enforce integration lane policy as required merge gate.
    status: pending
  - id: harden-release-trust
    content: Ensure release artifacts include SBOM, signature verification, and provenance with digest-based promotion.
    status: pending
  - id: run-aws-dev-loop
    content: Execute Terraform dev plan/apply/smoke/rollback documentation loop and capture reproducible commands.
    status: pending
  - id: validate-observability-resilience
    content: Define SLIs/SLOs, validate alerts, and run at least one controlled failure drill.
    status: pending
  - id: benchmark-high-load
    content: Run repeatable load scenarios and implement/document top 1-2 performance fixes.
    status: pending
  - id: extract-one-service
    content: Introduce one additional microservice with same SDLC gates only after ingestor quality gate criteria are met.
    status: pending
isProject: false
---

# Job-Ready SDLC Focus Plan (Post Phase-2)

## Goal

Land a backend/cloud-native role quickly by demonstrating end-to-end ownership of one shippable service (`ingestor`) with strong SDLC discipline, then extending that foundation with one additional microservice.

## Current Baseline (What to keep stable)

- Keep `ingestor` as the primary product surface and reliability anchor in [`/home/ivanp/PersonalProjects/data-pipeline-async/services/ingestor`](/home/ivanp/PersonalProjects/data-pipeline-async/services/ingestor).
- Use the existing local platform in [`/home/ivanp/PersonalProjects/data-pipeline-async/docker-compose.yml`](/home/ivanp/PersonalProjects/data-pipeline-async/docker-compose.yml) and operational command layer in [`/home/ivanp/PersonalProjects/data-pipeline-async/Justfile`](/home/ivanp/PersonalProjects/data-pipeline-async/Justfile).
- Treat the Phase-2 Floci sandbox as done and move to real AWS dev loop from [`/home/ivanp/PersonalProjects/data-pipeline-async/.github/prompts/plan-v02Roadmap.prompt.md`](/home/ivanp/PersonalProjects/data-pipeline-async/.github/prompts/plan-v02Roadmap.prompt.md).

## Priority Strategy (T-shaped / Pi-shaped)

- Deep pillar 1 (Backend core): FastAPI async internals, DB modeling, migrations, test architecture, API correctness.
- Deep pillar 2 (Platform/Cloud): Terraform + ECS deploys + CI/CD release trust chain.
- Broad horizontal: observability, resilience patterns, performance/load, security baseline, developer workflows.
- Avoid heavy enterprise-only investments for now (multi-team governance, advanced org-level platform abstractions, excessive IaC module granularity).

## Minimal Branch and Environment Matrix (Adopt now)

### Branch to environment mapping

- `feature/*` -> no environment deploy by default; run CI only.
- `develop` -> dev environment deployment target (Floci loop + AWS dev), QA validation happens here.
- `main` -> production release line; deploy to prod only from `main` tags/releases.

```text
feature/* -> PR -> ci.yml (full gates)
develop   -> push -> ci.yml + cd-dev.yml (auto deploy dev)
main      -> v* tag -> release.yml (trust gates) -> cd-prod.yml (manual approval)

v0.4 tag -> release.yml builds image@sha256:abc
         -> cd-dev deploys sha256:abc   (auto)
         -> cd-prod deploys sha256:abc  (manual approval)

```

### Minimal triggers and policies

- Pull request to `develop`:
  - Required: lint + unit.
  - Optional/non-blocking: e2e/nightly.
  - Integration can run here for faster feedback if budget allows.
- Push/merge to `develop`:
  - Required: integration + smoke-deploy.
  - If green: deploy to dev environment.
- QA cycle in dev:
  - QA tests on dev.
  - If bugs found: fix on `feature/*`, merge back into `develop`, redeploy dev, retest.
- Promotion to `main`:
  - Only after `develop` scope is validated and changelog/release notes prepared.
  - Promote same tested image digest (no rebuild).
- Release from `main`:
  - Required: release trust gates (SBOM, signature, provenance).
  - **`release.yml` has no branch guard** — a `v*` tag on `develop` would also trigger it. Convention: only cut `v*` tags from `main`. A branch assertion step (`github.ref` must start with `refs/heads/main`) will be added to `release.yml` when AWS deploy is live.
  - `release.yml` enforces a branch guard in the `verify-ci` job: asserts the tagged commit exists on `origin/main` via `git branch -r --contains`. A `v*` tag on `develop` will fail this check and abort before any build or push.
- `cd-prod.yml` repeats the same assertion as a second guard before the deploy step.


### Why this is minimal but production-relevant

- Mirrors real team flow (integration branch + QA + controlled prod line) without heavy release bureaucracy.
- Preserves fast iteration in dev while protecting prod stability.
- Gives clear interview narrative: “tested in dev, promoted by digest, released from main”.

## GitHub Branch Protection and Workflow Trigger Checklist (Minimal)

- Protect `main`:
  - Require pull request before merge.
  - Require passing checks: lint, unit, release-trust workflow.
  - Require up-to-date branch before merge.
  - Restrict direct pushes to `main`.
- Protect `develop`:
  - Require pull request before merge.
  - Require passing checks: lint, unit, integration, smoke-deploy.
  - Restrict direct pushes to `develop` except emergency maintainers.
- Workflow triggers:
  - PR -> `develop`: run lint + unit (plus optional integration preview).
  - Push to `develop`: run integration + smoke-deploy + deploy-dev workflow.
  - Tag on `main` (`v*`): run release workflow (SBOM/sign/provenance) and deploy-prod after gates.
- Environment protections:
  - `dev` environment: no manual approver required, but deployment gated by green workflow.
  - `prod` environment: required manual approval + protected secrets.
- Promotion policy:
  - Build image once in CI.
  - Promote by immutable digest from `develop`-validated candidate to `main` release.
  - Do not rebuild per environment.

### Automation-first note (use existing script, not manual UI)

- Use [`/home/ivanp/PersonalProjects/data-pipeline-async/scripts/tools/set-branch-protection-gh.sh`](/home/ivanp/PersonalProjects/data-pipeline-async/scripts/tools/set-branch-protection-gh.sh) as the source of truth for branch protection configuration.
- Recommended rollout:
  - Dry-run first: `scripts/tools/set-branch-protection-gh.sh`
  - Apply to both branches: `scripts/tools/set-branch-protection-gh.sh --branches main,develop --apply`
  - If needed for personal repo behavior, keep `--enforce-admins false` explicit.
- Keep branch protection settings scripted and re-runnable after workflow/check-name changes.

## Execution Roadmap (8-10 weeks)

### Stage 1: Reliability and CI trust first (Week 1-2)

- Stabilize test architecture and fixture boundaries exactly as already identified in [`/home/ivanp/PersonalProjects/data-pipeline-async/.github/prompts/plan-v02Roadmap.prompt.md`](/home/ivanp/PersonalProjects/data-pipeline-async/.github/prompts/plan-v02Roadmap.prompt.md).
- Make integration lane required on merge-to-`develop` (dev deploy gate), with `main` protected by release/trust gates; keep e2e scheduled/non-blocking.
- Keep one-command local reproducibility for each CI lane using `just` tasks.
- Compact docs to reduce attention overhead:
  - Create one canonical SDLC runbook page under `docs/` as the single source of truth.
  - Convert repeated docs to short index pages that link to canonical sections instead of rephrasing.
  - Add “Last reviewed” and owner line to each high-value runbook.
- Output artifact for interviews:
  - Short testing architecture note under `docs/dev/`.
  - CI policy note: what blocks PR vs what blocks release.

### Stage 2: Release and supply-chain baseline (Week 3)
- Keep using `deploy-audit` flow in [`/home/ivanp/PersonalProjects/data-pipeline-async/Justfile`](/home/ivanp/PersonalProjects/data-pipeline-async/Justfile).
- Enforce release trust signals: SBOM, image signing verification, provenance.
- Adopt immutable digest promotion policy in docs and workflow behavior.
- Output artifact for interviews:
  - “How we trust container releases” one-pager with exact CI gates.

### Stage 3: Real cloud SDLC loop (Week 4-5)
- Promote from Floci-only loop to AWS dev deployment using Terraform env flow from [`/home/ivanp/PersonalProjects/data-pipeline-async/infra/terraform/environments/dev/main.tf`](/home/ivanp/PersonalProjects/data-pipeline-async/infra/terraform/environments/dev/main.tf).
- Keep cost-aware defaults in dev (`enable_messaging=false`, minimal Fargate sizing).
- Run repeating loop: plan -> apply -> smoke checks -> fix -> redeploy.
- Output artifact for interviews:
  - Deploy runbook with rollback section and “known failure modes”.

### Stage 4: Observability + resilience as portfolio differentiator (Week 6-7)
- For `ingestor`, make telemetry actionable, not just present:
  - SLI/SLO set for availability, p95 latency, probe success, background queue health.
  - Alert rules with clear runbooks.
- Resilience drills:
  - DB/Redis/Kafka partial outage simulations.
  - Backpressure/rate-limit behavior under burst traffic.
  - Circuit-breaker and retry behavior verification.
- Output artifact for interviews:
  - Incident drill report: hypothesis, signal, mitigation, postmortem notes.

### Stage 5: Performance + async/high-load fundamentals (Week 8)
- Add reproducible load scenarios (light, medium, burst) for critical endpoints.
- Measure and document bottlenecks: DB pool pressure, cache hit ratio, queue lag, scheduler timing drift.
- Implement only high-ROI fixes (query/index tuning, concurrency config, cache TTL strategy).
- Output artifact for interviews:
  - Before/after perf report with key graphs and concrete tradeoffs.

### Stage 6: Microservice expansion (Week 9-10)
- Add exactly one new service from `examples/archived-services` as next vertical slice (recommend `webhook` first due to strong production-relevant concerns: auth, idempotency, replay, eventing).
- Keep strict service boundaries and shared contracts only through `libs/`.
- Integrate the same SDLC quality gates from `ingestor` (tests, CI path filters, release checks, smoke deploy).
- Output artifact for interviews:
  - “Service extraction decision and rollout” ADR + demo flow.

## Practical Focus Rules (What to spend time on vs skip)

### Invest heavily

- CI reliability and reproducibility.
- Cloud deploy + rollback confidence.
- Observability that helps diagnose real incidents.
- Async correctness and performance profiling.
- Security basics with strong ROI (secrets handling, authz, dependency/image scanning, least privilege).

### Keep lightweight for now

- Complex multi-account/multi-region platform design.
- Heavy GitOps/operator frameworks unless required for your immediate target jobs.
- Overly abstract internal platforms before 2-3 services actually need them.

## Weekly Learning Cadence (Theory + practice)

- 60% build/operate in this repo.
- 30% guided theory tied to current week’s implementation topic.
- 10% interview packaging (write concise architecture and incident narratives).
- End each week with:
  - one merged production-like improvement,
  - one measurable metric improvement,
  - one short “what I learned and why it matters in prod” note.

## Job-Readiness Evidence Pack (Must-have)

- Architecture narrative for `ingestor` and cloud deployment path.
- CI/CD pipeline explanation with trust gates and promotion policy.
- One incident/resilience case study.
- One performance tuning case study.
- One service extraction case study (after Stage 6).
- Clean README/docs pointers so interviewer can run and verify quickly.

## Decision Gate for adding more services

Only add service #2 after all are true:

- `ingestor` CI lanes stable for at least one full cycle.
- AWS dev deploy loop is repeatable without manual console patching.
- Observability alerts and runbooks validated by at least one drill.
- Release trust chain is green and reproducible.

## Suggested next immediate sequence (this week)

- Run and stabilize reliability/CI tasks first (fixture boundaries + integration gate).
- Re-run Floci plan/apply/destroy loop once as regression check.
- Execute first AWS dev `plan` and document expected resources/cost.
- Prepare one interview-ready diagram and one runbook from real outputs.
- Start docs compaction pass:
  - Identify duplicated SDLC/CI/deploy docs and mark one canonical file per topic.
  - Merge duplicate content into canonical files and replace duplicates with short pointers.
  - Keep each critical operational topic to one primary page + one checklist page maximum.

## Horizon View (How this evolves after MVP v0.2)

- Horizon A (now): single `ingestor` service, strict quality gates, reliable dev deploy loop.
- Horizon B (next): one additional service (`webhook`) with the same branch/deploy/release policy and shared contracts discipline.
- Horizon C (later): optional stage environment and stricter change controls only when traffic/team complexity justifies the extra process.

## Documentation Compaction Guardrails (Anti-duplication)

- One topic, one canonical document:
  - SDLC flow.
  - CI gates and branch policy.
  - Deployment runbook.
  - Incident response/checklists.
- Prefer checklists and link-based navigation over long repeated prose.
- If new doc content overlaps an existing section by more than ~30%, update existing canonical page instead of creating a new one.
- Keep docs interview-friendly:
  - include exact commands,
  - expected outputs/exit criteria,
  - rollback path.

## Concrete Docs Cleanup Map (Keep / Merge / Archive)

### Keep as canonical (single source)

- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/README.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/README.md) as global docs index.
- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/dev/commands.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/dev/commands.md) as the only command catalog (no command duplication elsewhere).
- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/03-daily-development.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/03-daily-development.md) as workflow narrative (link to commands page, do not repeat command blocks).
- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/floci-aws-deployment-workflow.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/floci-aws-deployment-workflow.md) as local sandbox canonical runbook.
- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/deployment/aws-ecs.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/deployment/aws-ecs.md) as real AWS deploy canonical runbook.
- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/deployment/cost-teardown.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/deployment/cost-teardown.md) as teardown/cost canonical checklist.
- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/04-architecture-overview.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/04-architecture-overview.md) as runtime architecture canonical page.
- Keep [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/adr/README.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/adr/README.md) as ADR entrypoint.

### Merge (deduplicate into canonical targets)

- Merge CI/CD and release policy overlap into one canonical page:
  - Canonical target: [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/ci/workflow-reference.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/ci/workflow-reference.md)
  - Merge in key non-duplicate content from:
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/github-actions-security-hardening.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/github-actions-security-hardening.md)
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/cicd-iac-gitops-portable-strategy.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/cicd-iac-gitops-portable-strategy.md)
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/versioning.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/versioning.md)
- Merge architecture duplication into one canonical runtime narrative:
  - Canonical target: [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/04-architecture-overview.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/04-architecture-overview.md)
  - Pull only unique decision context from:
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/architecture.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/architecture.md)
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/cloud-deployment.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/cloud-deployment.md)
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/monorepo-structure.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/monorepo-structure.md)
- Merge observability guidance:
  - Canonical target: [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/observability.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/observability.md)
  - Fold in relevant parts from:
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/pillar-4-observability.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/pillar-4-observability.md)
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/runbooks/slo-breach-response.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/runbooks/slo-breach-response.md) (keep runbook-specific action steps in runbooks).
- Merge setup overlap:
  - Canonical target: [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/01-system-setup.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/01-system-setup.md) + [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/02-first-time-setup.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/02-first-time-setup.md)
  - Convert these to link-first wrappers around:
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/setup/system-requirements.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/setup/system-requirements.md)
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/setup/environment-setup.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/setup/environment-setup.md)
    - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/setup/local-https-setup.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/setup/local-https-setup.md)

### Archive (or convert to 5-10 line pointer pages)

- Candidate archive/pointer set for strategy-heavy duplicates:
  - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/project-evolution-and-growth-playbook.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/project-evolution-and-growth-playbook.md)
  - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/be-learning-knowledge-base.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/design/be-learning-knowledge-base.md)
  - [`/home/ivanp/PersonalProjects/data-pipeline-async/docs/09-backend-concepts-and-patterns.md`](/home/ivanp/PersonalProjects/data-pipeline-async/docs/09-backend-concepts-and-patterns.md)
- Candidate archive for alternate/duplicate ADR copies:
  - Keep one ADR location canonical (`docs/adr/`), convert `docs/design/adr/*` to short pointers (or remove after link migration).
- Candidate archive for personal/career docs from engineering index:
  - Keep under `docs/personal/` but remove from core engineering reading path in `docs/README.md`.

### Frictionless execution sequence (docs compaction sprint)

- Pass 1 (inventory): tag each doc as `canonical`, `merge-into:<target>`, or `archive-pointer`.
- Pass 2 (merge): copy only unique content into canonical targets, avoid rephrasing duplicates.
- Pass 3 (shrink): reduce merged docs to short pointer pages with 1-paragraph purpose + canonical link.
- Pass 4 (navigation): update `docs/README.md` so every track points to canonical pages only.
- Pass 5 (quality): verify no topic has more than one command-heavy page.

## Phase-by-Phase Compact Docs Cleanup Backlog

### Phase A: CI and release docs compaction

- Scope:
  - `docs/ci/workflow-reference.md`
  - `docs/github-actions-security-hardening.md`
  - `docs/cicd-iac-gitops-portable-strategy.md`
  - `docs/versioning.md`
- Timebox: 0.5-1 day.
- Actions:
  - Keep `docs/ci/workflow-reference.md` canonical.
  - Merge unique release/trust/promotion content from the other three files.
  - Convert merged files to short pointer pages.
- Done when:
  - One canonical CI/release page exists.
  - No duplicated branch-policy or release-gate prose remains.

### Phase B: deployment runbooks compaction

- Scope:
  - `docs/floci-aws-deployment-workflow.md`
  - `docs/deployment/aws-ecs.md`
  - `docs/deployment/cost-teardown.md`
  - `docs/cloud-deployment.md`
- Timebox: 0.5-1 day.
- Actions:
  - Keep Floci local flow, AWS ECS deploy flow, and teardown as three canonical runbooks.
  - Move strategy-only overlap into `docs/cloud-deployment.md` and strip duplicate commands from strategy page.
  - Ensure each runbook has prerequisites, commands, exit criteria, rollback/teardown.
- Done when:
  - No deploy command block appears in more than one runbook for the same flow.
  - Dev and prod pathways are unambiguous.

### Phase C: architecture docs compaction

- Scope:
  - `docs/04-architecture-overview.md`
  - `docs/design/architecture.md`
  - `docs/monorepo-structure.md`
  - `docs/design/system-design-c4.md`
- Timebox: 1 day.
- Actions:
  - Keep `docs/04-architecture-overview.md` as runtime canonical.
  - Keep `docs/design/system-design-c4.md` for diagram depth only.
  - Merge unique content from `docs/design/architecture.md` and `docs/monorepo-structure.md` into canonical pages.
  - Convert redundant architecture pages into concise pointers.
- Done when:
  - Interview narrative can be told from 2 pages max (runtime overview + C4 deep-dive).

### Phase D: setup and daily workflow compaction

- Scope:
  - `docs/01-system-setup.md`
  - `docs/02-first-time-setup.md`
  - `docs/03-daily-development.md`
  - `docs/setup/system-requirements.md`
  - `docs/setup/environment-setup.md`
  - `docs/dev/commands.md`
- Timebox: 0.5-1 day.
- Actions:
  - Keep `docs/dev/commands.md` as only command catalog.
  - Keep `docs/setup/*` as setup source of truth.
  - Convert `01/02/03` pages into lightweight onboarding flow that links to canonical setup and commands pages.
- Done when:
  - New contributor can onboard with one reading path and zero command duplication.

### Phase E: observability and runbooks compaction

- Scope:
  - `docs/observability.md`
  - `docs/design/pillar-4-observability.md`
  - `docs/runbooks/slo-breach-response.md`
  - `docs/runbooks/circuit-breaker-triggered.md`
  - `docs/runbooks/dlq-replay.md`
  - `docs/runbooks/chaos-testing.md`
- Timebox: 0.5-1 day.
- Actions:
  - Keep `docs/observability.md` canonical for telemetry model and SLO definitions.
  - Keep `docs/runbooks/*` canonical for incident procedures.
  - Remove conceptual duplication from runbooks; keep only action steps, triggers, and verification.
- Done when:
  - Every alert maps to exactly one runbook.
  - Observability concepts are centralized in one page.

### Phase F: ADR and long-tail cleanup
- Scope:
  - `docs/adr/*`
  - `docs/design/adr/*`
  - `docs/personal/*` references from engineering index
  - orphan/low-signal docs identified in prior phases
- Timebox: 0.5 day.
- Actions:
  - Keep `docs/adr/` as only ADR location.
  - Convert `docs/design/adr/*` into pointers (or remove after link migration).
  - Remove `docs/personal/*` from core engineering navigation and keep as separate track.
- Done when:
  - No duplicate ADR trees remain in active navigation.
  - Engineering docs index is focused and compact.

### Execution rhythm and constraints
- Run one phase per day maximum; do not mix phases unless a file is a direct dependency.
- At phase end, update `docs/README.md` before moving forward.
- Enforce “one topic -> one canonical doc” before accepting any new docs PR.

## Docs Compaction Sprint Board (Single-Page Tracker)

Use this checklist as the only progress tracker for docs cleanup.

### Phase status board
- [ ] Phase A — CI and release docs compaction
  - Status: not started
  - Owner: 
  - Target date: 
  - Notes: 
- [ ] Phase B — deployment runbooks compaction
  - Status: not started
  - Owner: 
  - Target date: 
  - Notes: 
- [ ] Phase C — architecture docs compaction
  - Status: not started
  - Owner: 
  - Target date: 
  - Notes: 
- [ ] Phase D — setup and daily workflow compaction
  - Status: not started
  - Owner: 
  - Target date: 
  - Notes: 
- [ ] Phase E — observability and runbooks compaction
  - Status: not started
  - Owner: 
  - Target date: 
  - Notes: 
- [ ] Phase F — ADR and long-tail cleanup
  - Status: not started
  - Owner: 
  - Target date: 
  - Notes: 

### Weekly sprint cadence
- [ ] Week kickoff: pick exactly one phase as active phase.
- [ ] Midweek check: confirm canonical target pages are still single-source.
- [ ] Week close: mark completed phase, log blockers, and update next phase target date.

### Definition of complete for tracker
- [ ] All six phases checked complete.
- [ ] `docs/README.md` reflects canonical navigation only.
- [ ] No duplicated command-heavy content remains across docs topics.

## Copilot Control Plane (1-Week Cleanup Sequence)

Goal: make `.copilot/` + `.github/` guidance accurate, non-duplicative, and enforceable so AI output is consistently high quality.

### Day 1 — Audit
- Inventory all AI-control files:
  - `.copilot/*`
  - `.github/copilot-instructions.md`
  - `.github/instructions/*.instructions.md`
  - `.github/prompts/*.prompt.md`
  - `.github/hooks/*`
- Tag each file as:
  - `active-canonical`
  - `stale-template`
  - `duplicate-overlap`
- Output: one short audit note listing files to keep/update/archive.

### Day 2 — Normalize paths and repo references
- Update prompt/instruction references to current repo structure (e.g., `services/ingestor/*`, `libs/*`, `tests/*`, `alembic/*`).
- Remove references to obsolete template paths (e.g., generic `app/*` layouts) unless explicitly documented as examples.
- Output: path-consistent prompts/instructions aligned to actual codebase.

### Day 3 — De-duplicate instruction layers
- Keep one rule hierarchy:
  - global project rules in `.github/copilot-instructions.md`
  - domain rules in `.github/instructions/*`
  - reusable operator prompts in `.copilot/AGENT_COMMANDS.md`
- Merge overlapping guidance; keep shortest canonical wording.
- Replace duplicates with pointer lines to canonical files.
- Output: no repeated policy text across layers.

### Day 4 — Prompt quality hardening
- For each high-use prompt in `.github/prompts/`:
  - enforce clear input contract,
  - update expected file paths,
  - require validation/test step in prompt body,
  - add “smallest-change-first” constraint where relevant.
- Output: prompts produce reliable, repo-specific changes with lower drift.

### Day 5 — Hook enforcement alignment
- Align hook behavior in `.github/hooks/*` with canonical rules (security scan, governance checks, tool guardrails).
- Ensure hook docs explain:
  - what is enforced,
  - when it runs,
  - how to fix failures.
- Output: enforcement and written guidance match exactly.

### Day 6 — Dry-run validation loop
- Execute representative prompt scenarios (endpoint change, migration review, CI tweak, docs update) in dry-run/plan style.
- Check that generated guidance consistently references canonical files and current paths.
- Output: short validation matrix of “scenario -> expected behavior -> pass/fail”.

### Day 7 — Lock-in and maintenance policy
- Add maintenance note in plan/docs:
  - every structural refactor requires updating `.copilot/` + `.github/instructions/` + affected prompts in same PR.
- Add monthly lightweight review task for AI-control files.
- Output: sustainable process to prevent future drift.

### Success criteria
- Prompts/instructions reference current repo paths only.
- No duplicated policy prose across control files.
- Hook behavior and documented rules are consistent.
- AI sessions require less corrective steering and fewer “wrong-path” outputs.
