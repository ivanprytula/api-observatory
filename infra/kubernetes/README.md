# Local Kubernetes lab

This is a disposable k3d exercise, not the MVP runtime. Local Docker Compose
remains the canonical development workflow.

The lab needs Docker, k3d, and kubectl. It creates the `api-obs` cluster,
builds and publishes local images to the k3d registry, starts one ephemeral pgvector/PostgreSQL
database, runs Alembic, then deploys one ingestor and one dashboard.

```bash
just --justfile just/labs.just lab-k8s-up
curl http://ingestor.127.0.0.1.nip.io:8080/readyz
```

Then visit `http://dashboard.127.0.0.1.nip.io:8080` in a browser.

Use the lab-only debugging commands when needed:

```bash
just --justfile just/labs.just lab-k8s-status
just --justfile just/labs.just lab-k8s-logs ingestor
just --justfile just/labs.just lab-k8s-port-forward dashboard 8501 8501
```

Destroy the cluster and its `emptyDir` database data after the exercise:

```bash
just --justfile just/labs.just lab-k8s-down
```

HPA, network policies, Redis, Redpanda, and cloud deployment are deliberately
outside this lab. They need a separate, measured reason before becoming part
of an application runtime.
