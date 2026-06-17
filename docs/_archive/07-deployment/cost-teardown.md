# Deployment Cost Teardown

Track: C — Architecture and Platform Strategy

This page is the shutdown checklist for avoiding cloud and local sandbox spend after Phase 11 deployment work.

## Cost Guardrails

- Dev Terraform keeps MSK disabled by default (`enable_messaging = false`).
- Use sandbox validation only for short-lived test windows.
- Destroy all temporary infrastructure immediately after tests.

## Estimated Cost Envelope

| Profile | Approx daily cost | Notes |
| --- | ---: | --- |
| Local sandbox (Floci) | $0 | Local container only |
| AWS dev without MSK | ~$2.50/day | Network + baseline managed services |
| AWS dev with MSK | ~$5.14/day | Adds ~`$2.64/day` messaging cost |

## Local Teardown Commands

Use this order after sandbox validation:

```bash
TF_ENV=sandbox just tf destroy
just floci-down
docker compose down -v
```

## AWS Dev Teardown Commands

Run from [infra/terraform/environments/dev](../../infra/terraform/environments/dev):

```bash
terraform destroy
```

Then verify no residual billable endpoints remain:

1. ALB removed
2. ECS services removed
3. RDS instance removed
4. ElastiCache cluster removed
5. MSK resources removed (if enabled)

## Post-Teardown Verification

```bash
# no local sandbox containers
docker compose --profile aws ps

# no local Terraform state lock process
ls -la .terraform
```

## Safety Notes

- Never leave `terraform apply` environments idle overnight without a teardown decision.
- Keep `enable_messaging` off unless Kafka behavior is actively being tested.
- Prefer the local Floci workflow first, then promote to AWS only when test evidence is complete.
