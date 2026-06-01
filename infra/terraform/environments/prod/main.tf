terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {}
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "data-zoo"
      Environment = "prod"
      ManagedBy   = "terraform"
      Repository  = "api-observatory"
    }
  }
}

module "network" {
  source = "../../modules/network"

  project            = "data-zoo"
  environment        = "prod"
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  nat_gateway_count  = length(var.availability_zones)  # One NAT per AZ for resilience
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
  environment        = "prod"
  private_subnet_ids = module.network.private_subnet_ids
  sg_db_id           = module.network.sg_db_id
  instance_class     = "db.t3.medium"
  multi_az           = true
  backup_retention_days = 14
}

module "cache" {
  source = "../../modules/cache"

  project            = "data-zoo"
  environment        = "prod"
  private_subnet_ids = module.network.private_subnet_ids
  sg_cache_id        = module.network.sg_cache_id
  node_type          = "cache.t3.small"
  num_cache_clusters = 2  # Primary + replica for automatic failover
  auth_token         = var.redis_auth_token
}

module "messaging" {
  source = "../../modules/messaging"

  project            = "data-zoo"
  environment        = "prod"
  private_subnet_ids = module.network.private_subnet_ids
  sg_msk_id          = module.network.sg_msk_id
}

module "compute" {
  source = "../../modules/compute"

  project            = "data-zoo"
  environment        = "prod"
  aws_region         = var.aws_region
  vpc_id             = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  private_subnet_ids = module.network.private_subnet_ids
  sg_alb_id          = module.network.sg_alb_id
  sg_app_id          = module.network.sg_app_id

  ecr_repository_url_ingestor = module.ecr.repository_urls["ingestor"]
  image_tag                   = var.image_tag

  msk_cluster_arn     = module.messaging.cluster_arn
  acm_certificate_arn = var.acm_certificate_arn
  log_retention_days  = 90

  ingestor_cpu           = 512
  ingestor_memory        = 1024
  ingestor_desired_count = 2  # Minimum 2 for zero-downtime rolling deploys
}
