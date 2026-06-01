# MSK Serverless — Kafka-compatible, no broker management, pay-per-use.
# Compatible with aiokafka (used in app/events.py) via TLS on port 9098.

resource "aws_msk_serverless_cluster" "main" {
  cluster_name = "${var.project}-${var.environment}-kafka"

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.sg_msk_id]
  }

  client_authentication {
    sasl {
      iam {
        # IAM auth — no password to manage; ECS task role gets MSK policy
        enabled = true
      }
    }
  }

  tags = { Name = "${var.project}-${var.environment}-kafka" }
}
