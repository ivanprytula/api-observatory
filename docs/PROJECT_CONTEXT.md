# PROJECT_CONTEXT.md

Project direction, architectural tradeoffs, and engineering topic lookup guidance for api-observatory.

## Project direction

Keep this section current as the project evolves. It is the source of truth for product and architectural tradeoffs; do not infer missing decisions from it.

- **Primary users:** The repository is primarily a job-preparation playground for a Python backend
  engineer progressing from Strong Middle toward Senior/Lead depth. A solo SaaS developer monitoring
  third-party dependencies is the standing product example, not a commitment to run a startup.
- **Near-term goals:** Keep an evidence-backed engineering topic index; own the critical request,
  data, messaging, failure, and deployment flows; add one tenant-safe dependency-incident vertical
  slice; retain an interview-ready demo and architecture defence.
- **Non-goals:** Maximizing technology count, implementing scale-only patterns without measured
  triggers, customer acquisition, billing, permanent hosting, or claiming production ownership from
  repository/configuration evidence.
- **Architecture trajectory:** Preserve the simplest operational shape that demonstrates the current
  behavior. Extract services, add managed platforms, or shard data only after an explicit capacity,
  availability, ownership, or deployment trigger is measured.
- **Data posture:** Tenant isolation is deny-by-default and extended table by table. Avoid collecting
  unnecessary PII or secrets; retention work must be bounded, verifiable, and reversible.
- **Integration policy:** Version shared contracts, bound every network call, retry only safe work,
  and keep external AI/cache/broker integrations optional or fail-open where documented.
- **Deployment target:** Local Compose is canonical. The only active cloud direction is the AWS MVP:
  ECR plus one private, SSM-operated EC2 Compose host, PostgreSQL on encrypted EBS, Parameter Store,
  and retained S3 backups. It remains a decision/configuration claim until a separately approved live
  deployment is verified. The learning sequence is EC2, then ECS on Fargate, then EKS; another IaaS
  provider is out of scope until that sequence has exercised evidence.
- **Quality bar:** Focused unit/integration tests, migration compatibility, authorization regression
  coverage, measured performance claims, failure/recovery evidence, observability, diff review, and a
  blocking secrets scan.

## Evergreen topic lookup

Use `docs/02-architecture/engineering-topics.md` as the canonical index for questions such as
"Where is sharding?" or "How does load balancing work here?" Verify the current checkout before
answering; the index routes discovery but is not a substitute for source evidence.

Answer topic lookups in this order:

1. **Status:** `Core`, `Lab`, `Decision`, `Deferred`, or `Historical`.
2. **Where:** exact current implementation, tests, configuration, and ADR/runbook paths.
3. **How it works here:** project-specific behavior and data flow.
4. **What is missing:** distinguish tested runtime behavior from configuration or an idea.
5. **Why this design:** current constraint, tradeoff, and rejected complexity.
6. **Scale trigger:** measurable evidence required before changing the design.
7. **Learning exercise:** one bounded test, fault, or local experiment.
8. **Interview check:** questions the user should answer without AI.

Archived files can explain history but cannot prove current functionality. Never describe a lab,
manifest, Terraform plan, or unexecuted deployment workflow as production experience. When a topic
mixes implemented and deferred concepts (for example table partitioning versus database sharding),
state each boundary explicitly.
