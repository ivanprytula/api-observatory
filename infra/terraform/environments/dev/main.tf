terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # State stored in S3 with DynamoDB locking.
  # Apply backend config:
  #   terraform init -backend-config="bucket=<your-state-bucket>" \
  #                  -backend-config="key=data-zoo/dev/terraform.tfstate" \
  #                  -backend-config="region=eu-central-1" \
  #                  -backend-config="dynamodb_table=<your-lock-table>"
  backend "s3" {}
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile  # Named profile — never use 'default' for project work

  default_tags {
    tags = {
      Project     = "data-zoo"
      Environment = "dev"
      ManagedBy   = "terraform"
      Repository  = "data-pipeline-async"
    }
  }
}

# ── Modules ───────────────────────────────────────────────────────────────────

module "network" {
  source = "../../modules/network"

  project            = "data-zoo"
  environment        = "dev"
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  nat_gateway_count  = 1    # Single NAT — saves ~$32/month in dev
  app_port           = 8000
}

module "ecr" {
  source  = "../../modules/ecr"
  project = "data-zoo"
}

module "iam" {
  source            = "../../modules/iam"
  project           = "data-zoo"
  aws_region        = var.aws_region
  github_repository = var.github_repository
}

module "database" {
  source = "../../modules/database"

  project            = "data-zoo"
  environment        = "dev"
  private_subnet_ids = module.network.private_subnet_ids
  sg_db_id           = module.network.sg_db_id
  instance_class     = "db.t3.micro"
  multi_az           = false
  backup_retention_days = 3
}

module "cache" {
  source = "../../modules/cache"

  project            = "data-zoo"
  environment        = "dev"
  private_subnet_ids = module.network.private_subnet_ids
  sg_cache_id        = module.network.sg_cache_id
  node_type          = "cache.t3.micro"
  num_cache_clusters = 1
  auth_token         = var.redis_auth_token
}

module "messaging" {
  count  = var.enable_messaging ? 1 : 0
  source = "../../modules/messaging"

  project            = "data-zoo"
  environment        = "dev"
  private_subnet_ids = module.network.private_subnet_ids
  sg_msk_id          = module.network.sg_msk_id
}

module "compute" {
  source = "../../modules/compute"

  project            = "data-zoo"
  environment        = "dev"
  aws_region         = var.aws_region
  vpc_id             = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  private_subnet_ids = module.network.private_subnet_ids
  sg_alb_id          = module.network.sg_alb_id
  sg_app_id          = module.network.sg_app_id

  ecr_repository_url_ingestor = module.ecr.repository_urls["ingestor"]
  image_tag                   = var.image_tag

  # Cost guard: keep MSK disabled in dev by default (~$2.64/day saved).
  msk_cluster_arn     = var.enable_messaging ? module.messaging[0].cluster_arn : ""
  acm_certificate_arn = var.acm_certificate_arn
  log_retention_days  = 14

  # Dev: minimal sizing — Fargate Spot selected automatically by capacity_provider_strategy
  ingestor_cpu           = 256
  ingestor_memory        = 512
  ingestor_desired_count = 1
}
