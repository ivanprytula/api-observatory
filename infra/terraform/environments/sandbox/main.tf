# CLOUD PROVIDER: hashicorp/aws ~> 5.0
# To switch providers: replace the required_providers block and the provider block below.
# Variables, module calls, and file names are provider-neutral and stay unchanged.

terraform {
  required_version = ">= 1.9"

  # CLOUD PROVIDER: update source/version here when switching clouds.
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # CLOUD PROVIDER: backend type ("s3", "gcs", "azurerm") changes here.
  # backend.hcl content also changes — file name stays backend.hcl.
  backend "s3" {}
}

# CLOUD PROVIDER: replace this block when switching (e.g. provider "google" or provider "azurerm").
provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile  # [sandbox] profile — never collide with real credentials

  # Redirect all API calls to the local emulator endpoint.
  endpoints {
    s3  = var.emulator_endpoint
    ecr = var.emulator_endpoint
    ecs = var.emulator_endpoint
    iam = var.emulator_endpoint
    rds = var.emulator_endpoint
    sts = var.emulator_endpoint
  }

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true

  default_tags {
    tags = {
      Project     = "data-zoo"
      Environment = "sandbox"
      ManagedBy   = "terraform"
      Repository  = "api-observatory"
    }
  }
}

# ── Modules ───────────────────────────────────────────────────────────────────

module "network" {
  source = "../../modules/network"

  project            = "data-zoo"
  environment        = "sandbox"
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  nat_gateway_count  = 0  # no NAT in local sandbox
  app_port           = 8000
}

module "ecr" {
  source   = "../../modules/ecr"
  project  = "data-zoo"
  services = var.ecr_services
}

module "iam" {
  count  = var.enable_iam ? 1 : 0
  source = "../../modules/iam"

  project           = "data-zoo"
  aws_region        = var.aws_region
  github_repository = var.github_repository
}

module "database" {
  count  = var.enable_database ? 1 : 0
  source = "../../modules/database"

  project            = "data-zoo"
  environment        = "sandbox"
  private_subnet_ids = module.network.private_subnet_ids
  sg_db_id           = module.network.sg_db_id
  instance_class     = "db.t3.micro"
  multi_az           = false
  backup_retention_days        = 0
  create_subnet_group          = false
  db_subnet_group_name         = var.db_subnet_group_name
  manage_master_user_password  = false
  master_password              = var.db_master_password
}

module "cache" {
  count  = var.enable_cache ? 1 : 0
  source = "../../modules/cache"

  project            = "data-zoo"
  environment        = "sandbox"
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
  environment        = "sandbox"
  private_subnet_ids = module.network.private_subnet_ids
  sg_msk_id          = module.network.sg_msk_id
}

module "compute" {
  source = "../../modules/compute"

  project            = "data-zoo"
  environment        = "sandbox"
  aws_region         = var.aws_region
  vpc_id             = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  private_subnet_ids = module.network.private_subnet_ids
  sg_alb_id          = module.network.sg_alb_id
  sg_app_id          = module.network.sg_app_id

  ecr_repository_url_ingestor = module.ecr.repository_urls["ingestor"]
  ecr_repository_url_dashboard = module.ecr.repository_urls["dashboard"]
  image_tag                   = var.image_tag
  ingestor_service_name       = "ingestor"

  msk_cluster_arn     = var.enable_messaging ? module.messaging[0].cluster_arn : ""
  acm_certificate_arn = ""
  log_retention_days  = 1

  ingestor_cpu           = 256
  ingestor_memory        = 512
  ingestor_desired_count = 1
  dashboard_cpu          = 256
  dashboard_memory       = 512
  dashboard_desired_count = 1
}
