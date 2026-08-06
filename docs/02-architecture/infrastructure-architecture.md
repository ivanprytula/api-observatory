# AWS MVP Delivery Architecture

The current AWS MVP boundary deliberately separates application delivery from platform operations.
It is a **Decision** contract until a separately approved live run supplies operational evidence.

| Application repository | Infrastructure repository |
| --- | --- |
| CI, immutable images, reviewed `aws-dev` lock, Compose workload, migrations, readiness, smoke checks, application rollback, Prometheus workload configuration | Terraform, networking, EC2/RDS/ECR/S3, IAM, Parameter Store, Docker/SSM bootstrap, host recovery, backup/restore tooling, infrastructure monitoring |

The app's desired state is the reviewed lock at
[`environments/aws-dev/images.lock.json`](../../environments/aws-dev/images.lock.json). A green
lock merge invokes the app deployment workflow, which validates the exact committed source and ECR
digests before sending its workload assets through SSM. The host is not a pull-based GitOps agent;
Git remains the versioned source of desired state and GitHub Actions performs the controlled push.

Platform contract `1` provides `/opt/api-observatory-mvp`, its protected `.runtime` directory,
Docker Compose, SSM access, and `api-observatory-mvp-render-env <group>...`. Application code decides
which groups are needed from the reviewed profiles. Platform code owns how Parameter Store values are
rendered and how the host is replaced or recovered.

`mvp` names the present workload scope. `aws-dev` names the environment. Future `aws-qa-stage` and
`aws-prod` should promote the same immutable digests after their own acceptance and approval gates;
they must not rebuild images.
