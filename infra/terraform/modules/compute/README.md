# Compute Module — Swappable ECS/EKS Backends

This module provisions container runtime infrastructure with pluggable backend support.

## Supported Compute Backends

| Backend       | Use Case                            | Ops Burden | Cost (dev) | Status             |
| ------------- | ----------------------------------- | ---------- | ---------- | ------------------ |
| `ecs-fargate` | Serverless containers, low ops      | None       | ~$10–30/mo | ✅ Production-ready|
| `ecs-ec2`     | Reserved instances, cost-sensitive  | Medium     | ~$5–15/mo  | ✅ Available       |
| `eks`         | Kubernetes, multi-cloud portability | High       | ~$70+/mo   | 🚧 Planned         |

## Usage

### Fargate (default, low-ops)

```hcl
module "compute" {
  source = "../../modules/compute"

  # ... standard variables ...

  compute_type = "ecs-fargate"  # Default

  # Fargate-specific
  fargate_capacity_provider = "FARGATE"  # or FARGATE_SPOT for dev
}
```

### EC2 (cost-optimized)

```hcl
module "compute" {
  source = "../../modules/compute"

  # ... standard variables ...

  compute_type = "ecs-ec2"

  # EC2-specific
  ec2_instance_type    = "t3.medium"
  ec2_desired_capacity = 2
  ec2_spot_price       = "0.05"  # For spot instances
}
```

### EKS (full Kubernetes)

```hcl
module "compute" {
  source = "../../modules/compute"

  # ... standard variables ...

  compute_type = "eks"

  # EKS-specific
  eks_version          = "1.29"
  eks_instance_type    = "t3.medium"
  eks_desired_size     = 2
}
```

## Outputs

All backends expose the same interface:

```hcl
output "cluster_id" {
  value = module.compute.cluster_id
}

output "cluster_endpoint" {
  value = module.compute.cluster_endpoint
}

output "alb_dns_name" {
  value = module.compute.alb_dns_name  # ECS only
}

output "ingress_class" {
  value = module.compute.ingress_class  # EKS only
}
```

## Migration Path

1. **Start on Fargate** (this repo's default)
2. **Test on EC2** by changing `compute_type = "ecs-ec2"`
3. **Move to EKS** when cloud portability becomes a priority

Terraform state is preserved; no data loss during backend switches.

## Design Notes

- Each backend must implement the same output interface
- Use `count` or `for_each` for conditional resource creation
- ALB/ingress configuration differs per backend (ECS: ALB, EKS: nginx-ingress)
- Task definitions (ECS) ↔ Deployments (EKS) are backend-specific
