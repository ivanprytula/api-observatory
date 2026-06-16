# ADR 008: ECS Fargate vs EKS for Cloud Compute

Track: C — Architecture and Platform Strategy


**Date**: April 22, 2026
**Status**: Accepted
**Context**: Phase 7 requires deploying 5 microservices to AWS with zero-downtime updates, multi-environment support (dev/prod), and minimal operational overhead.

---

## Problem

Which AWS container orchestration service should we use?

- **ECS Fargate**: Managed container orchestration, no node management, simpler API
- **EKS**: Kubernetes on AWS, powerful but higher ops burden

---

## Decision

### Use ECS Fargate for this project

#### Rationale

| Factor                | ECS Fargate                       | EKS                                      | Winner                     |
| --------------------- | --------------------------------- | ---------------------------------------- | -------------------------- |
| **Ops Burden**        | None (managed by AWS)             | High (node upgrades, CNI, control plane) | Fargate                    |
| **Learning Curve**    | Low (ALB, IAM, ECS API)           | High (K8s API, CRDs, RBAC)               | Fargate                    |
| **Setup Time**        | 1 hour (Terraform)                | 4 hours (Terraform + configuration)      | Fargate                    |
| **Cost (dev)**        | ~$85/month (Spot instances)       | ~$100+/month (control plane + nodes)     | Fargate                    |
| **Cost (prod)**       | ~$280/month (On-Demand)           | ~$400+/month (control plane + nodes)     | Fargate                    |
| **CI/CD Integration** | `aws ecs update-service` (simple) | `kubectl set image` + GitOps (complex)   | Fargate                    |
| **Service Count**     | Ideal for 1–10 services           | Ideal for 50+ services                   | Fargate (for this project) |
| **Auto-scaling**      | Manual + ALB target group         | Native Kubernetes HPA                    | EKS                        |

#### Why Not EKS?

1. **Overkill for 5 services** — Kubernetes adds complexity without corresponding benefit
2. **Distraction from learning** — Node management, CRD configuration, and CNI setup distract from distributed systems patterns
3. **Ops burden** — Requires platform team skills; this project focuses on service architecture
4. **Higher baseline cost** — EKS control plane is $73/month minimum, even with 0 nodes

---

## Consequences

### Positive

- ✅ **Fast deployment**: Terraform provisions infrastructure in 5 minutes
- ✅ **Low maintenance**: AWS handles patches, upgrades, failover
- ✅ **Cost-effective**: 70% cheaper in dev via Fargate Spot instances
- ✅ **Simple CI/CD**: Single `aws ecs update-service` call per deploy
- ✅ **Team-friendly**: New developers don't need K8s expertise
- ✅ **Zero-downtime updates**: ALB health checks + rolling deployment policy
- ✅ **Integrated observability**: CloudWatch Logs, Container Insights, CloudWatch Metrics

### Negative

- ❌ **Less flexible**: Can't customize CNI, no daemonset equivalent, limited scheduling control
- ❌ **Not idempotent on node failures**: If node dies, ECS reschedules; if AZ dies, you need Multi-AZ setup
- ❌ **Kubernetes skills unused**: If team has K8s expertise, it sits idle
- ❌ **Service mesh complexity**: Istio/Linkerd integration is harder (and not needed at scale of 5 services)
- ❌ **Future migration cost**: If we outgrow Fargate (50+ services), migrating to EKS is non-trivial

---

## Migration Path (if needed)

If this project grows to 50+ microservices and Fargate becomes a bottleneck:

1. **Keep current Terraform**
   - Extract `modules/compute` into separate ECS stack
   - Parallel setup of EKS cluster (new Terraform module)

2. **Gradual migration**
   - Deploy new services to EKS
   - Leave legacy services on Fargate during transition
   - Migrate service by service over weeks

3. **Estimated effort**: 2–3 days per engineer (familiar with both)

**Verdict**: Migration is possible but not trivial. This decision assumes the project stays at ~5 services. If requirements change, this ADR should be revisited.

---

## Alternatives Considered

### 1. Self-Managed EC2 + Docker Compose

- ❌ Full ops burden (patching, monitoring, failover)
- ❌ No auto-scaling
- ❌ Higher cost ($400+/month for always-on instances)
- ✅ Maximum flexibility

### 2. Lambda (Serverless Compute)

- ❌ Cold starts (15s–30s latency for infrequently used services)
- ❌ 15-minute execution timeout (not suitable for long-running processor)
- ❌ Complex async orchestration (Step Functions)
- ✅ Ultra-low ops burden for simple APIs

### 3. App Engine / Cloud Run (GCP / AWS equivalent)

- ❌ Vendor lock-in (harder to migrate if needed)
- ✅ Simpler than EKS
- ❌ Less mature observability integration
- ❌ Fewer deployment options (no multi-region failover)

---

## Related Decisions

- [ADR 005: GitHub OIDC vs Long-Lived Keys](005-github-oidc-vs-long-lived-keys.md) (CI/CD auth)

---

## References

- [ECS Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
- [EKS Pricing](https://aws.amazon.com/eks/pricing/)
- [AWS ECS Best Practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)
- [Fargate vs EKS Comparison](https://aws.amazon.com/blogs/containers/which-aws-container-service-should-i-use/)
