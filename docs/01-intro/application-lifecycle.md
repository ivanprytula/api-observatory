# Application Lifecycle and SDLC Drive-Through

API Observatory is easier to remember as a system that changes over time than as a list of
technologies. This guide follows the durable artifacts from product idea through delivery, operation,
and evidence-driven transformation; see the [README](../../README.md) for project purpose and audience.

## Lifecycle

```mermaid
flowchart LR
    Value["Value\nuser risk"] --> Requirements["Requirements\nbehavior + proof"]
    Requirements --> Design["Design\nboundaries + ADR"]
    Design --> Build["Build\ncode + data"]
    Build --> Verify["Verify\ntests + CI"]
    Verify --> Deliver["Deliver\nimage + contract"]
    Deliver --> Operate["Operate\nsignals + recovery"]
    Operate --> Evolve["Maintain / transform\nmeasured trigger"]
    Evolve --> Value
```

## 1. Value

The smallest useful problem is not “build a distributed system.” It is “help a developer detect
and understand third-party API failure before users report it.” The resulting behavior is bounded:

- register an external API dependency;
- probe availability, latency, and response shape;
- group repeated failures into tenant-scoped incidents;
- show what changed and what needs attention;
- exclude billing, customer acquisition, permanent hosting, and speculative scale work.

See the [user guide](../09-user-guides/user-guide.md) for the operator-facing workflow.

## 2. Requirements and Planning

A change is planned as a vertical slice: `value → behavior → data → dependencies → failure → proof`.
For dependency incidents that means persisted state and ownership, tenant-safe API behavior,
deduplication under concurrent signals, bounded notification failure, telemetry, tests, and a
rollback-compatible migration.

The [current roadmap](../03-planning/mvp-roadmap.md) owns priorities and adoption triggers. It does
not reproduce transient project tracking.

## 3. Design

The ingestor owns the public API, scheduler, incidents, and optional agent. Inference is a separate
HTTP service with its own PostgreSQL database; the dashboard is a client; MCP is a local stdio
client. Significant choices are recorded in the [decision summary](../02-architecture/decisions.md)
and linked ADRs.

The repository boundary is also a contract; see the [ownership table](../../README.md#repository-ownership) in the README and the [application deployment contract](../07-deployment/app-repo-contract.md) for the exact boundary.

Changes to ports, images, health endpoints, configuration names, ingress, IAM, secrets, or
telemetry must be checked against the app-owned
[deployment contract](../07-deployment/app-repo-contract.md).

## 4. Build

Implementation follows the slice through every affected layer rather than treating an endpoint as
the whole feature:

`migration → model/repository → service → authorization → API/UI → telemetry → documentation`

A schema change includes compatibility and rollback. A network call includes a timeout and failure
behavior. A cross-process schema includes contract versioning. Tenant isolation remains
deny-by-default. The [application architecture](../02-architecture/application-architecture.md)
maps these responsibilities to the current source tree.

## 5. Verify

- Unit tests prove deterministic behavior and failures.
- Integration tests prove database, migration, authorization, and service boundaries.
- Contract tests protect schemas and app/infra assumptions.
- Smoke, performance, and fault checks provide bounded runtime evidence.
- Security, dependency, image, and secret scans protect delivery inputs.

Passing configuration or a Terraform plan is not runtime proof. Use the
[development workflows](../05-development/dev-workflows.md),
[CI/CD reference](../06-ci-cd/ci-cd.md), and
[performance/failure worksheet](../05-development/performance-and-failure-lab.md) for proof.

## 6. Release and Delivery

Application CI validates deployable images without publishing them. After a deployable `main` change passes CI, a separately gated publisher builds immutable `tree-<SHA>` images and maintains a same-repo reviewed `aws-dev` lock PR. Merging that PR is the human release decision; a green app `main` CI run then deploys the exact merged lock to the pre-bootstrapped EC2 Compose host. Delivery is an in-place recreate with best-effort rollback; it is not rolling, blue/green, canary, or zero-downtime. See the [application deployment contract](../07-deployment/app-repo-contract.md) and the [infrastructure deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md) for the full boundary.

## 7. Operate

Operation needs health/readiness, structured logs, metrics, traces, alerts, persisted incident
state, and recovery procedures. The app defines signal meaning; infrastructure owns
production-oriented collection and routing. Current monitoring assets are local/configuration
evidence unless a live environment is separately exercised.

Start with [application observability](../08-operations/observability.md), then use the infra
[observability guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/operations/observability.md)
and recovery guide for platform actions.

## 8. Maintain and Transform

Maintenance covers dependency upgrades, security review, migrations, retention, backup/restore,
failure rehearsal, and removal of obsolete paths. Transformation changes a service boundary,
runtime, data strategy, or UI only after measured pressure.

1. Measure the user, reliability, capacity, ownership, or delivery problem.
2. Improve the current shape first when it can meet the target safely.
3. Record compatibility, rollback, and the rejected alternative.
4. Update both repositories when their contract moves.
5. Re-run behavior, failure, security, delivery, and recovery proof.

Valid triggers include repeated Compose deployment friction, independent workload scaling, a new
ownership boundary, a recovery objective beyond one region, or a measured database limit after
query/index/retention work. Technology interest alone is not a trigger.

## Interview Drive-Through

1. State the user problem and risk.
2. Trace one incident from requirement to data, API, UI, and telemetry.
3. Explain the app/infra boundary.
4. Show one test, one recovery path, and one immutable delivery contract.
5. Separate local runtime, labs, unexecuted AWS MVP, and deferred transformation.
6. End with the measurement that would justify the next architecture change.

The [interview package](interview-package.md) turns this lifecycle into a shorter live tour.
