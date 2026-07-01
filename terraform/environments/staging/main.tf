# =============================================================================
# DataPilot — Staging Environment
#
# Single shared NAT gateway, no Multi-AZ on RDS/ElastiCache, smaller node
# pools, and SPOT capacity for workers — staging optimises for cost over
# the high availability guarantees production needs.
# =============================================================================

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "datapilot-terraform-state"   # see ../../shared/backend.tf for bootstrap steps
    key            = "staging/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    use_lockfile     = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      Environment = var.environment
      ManagedBy   = "terraform"
    })
  }
}

locals {
  common_tags = merge(var.tags, { Environment = var.environment })
}

# -----------------------------------------------------------------------------
# Networking
# -----------------------------------------------------------------------------
module "vpc" {
  source = "../../modules/vpc"

  name_prefix                = var.name_prefix
  aws_region                 = var.aws_region
  cluster_name                = var.cluster_name
  vpc_cidr                    = var.vpc_cidr
  az_count                    = 2     # staging spans 2 AZs, production spans 3
  single_nat_gateway          = true  # cost optimisation — single NAT for staging
  enable_interface_endpoints  = false # skip interface endpoints in staging to save ~$22/mo each
  tags                        = local.common_tags
}

# -----------------------------------------------------------------------------
# EKS cluster
# -----------------------------------------------------------------------------
module "eks" {
  source = "../../modules/eks"

  name_prefix         = var.name_prefix
  cluster_name        = var.cluster_name
  kubernetes_version  = var.kubernetes_version
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids

  enable_public_endpoint = true
  public_access_cidrs    = ["0.0.0.0/0"] # tighten to office/VPN CIDRs once known

  core_instance_types = ["m6i.large"]
  core_desired_size   = 1
  core_min_size       = 1
  core_max_size       = 3

  worker_instance_types = ["m6i.xlarge"]
  worker_capacity_type  = "SPOT" # staging uses spot for cost savings
  worker_desired_size   = 1
  worker_min_size       = 1
  worker_max_size       = 4

  log_retention_days = 14
  tags                = local.common_tags
}

# -----------------------------------------------------------------------------
# Data layer
# -----------------------------------------------------------------------------
module "rds" {
  source = "../../modules/rds"

  name_prefix                    = var.name_prefix
  vpc_id                         = module.vpc.vpc_id
  private_subnet_ids             = module.vpc.private_subnet_ids
  eks_cluster_security_group_id  = module.eks.cluster_security_group_id

  instance_class           = "db.t4g.large"
  allocated_storage_gb     = 50
  max_allocated_storage_gb = 200
  multi_az                 = false # single-AZ in staging
  backup_retention_days    = 3
  deletion_protection      = false

  tags = local.common_tags
}

module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix                    = var.name_prefix
  vpc_id                         = module.vpc.vpc_id
  private_subnet_ids             = module.vpc.private_subnet_ids
  eks_cluster_security_group_id  = module.eks.cluster_security_group_id
  node_type           = "cache.t4g.medium"
  num_shards          = 1
  replicas_per_shard  = 0 # no replica in staging
  multi_az            = false

  tags = local.common_tags
}

module "msk" {
  source = "../../modules/msk"

  name_prefix                    = var.name_prefix
  vpc_id                         = module.vpc.vpc_id
  private_subnet_ids             = module.vpc.private_subnet_ids
  eks_cluster_security_group_id  = module.eks.cluster_security_group_id

  broker_count          = 2 # minimum for an MSK cluster; matches 2-AZ staging VPC
  broker_instance_type  = "kafka.t3.small"
  broker_ebs_volume_gb  = 100
  enhanced_monitoring   = "DEFAULT"

  tags = local.common_tags
}

module "s3" {
  source = "../../modules/s3"

  name_prefix           = var.name_prefix
  account_suffix        = var.account_suffix
  cors_allowed_origins  = var.cors_allowed_origins

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# IAM — application IRSA + scoped Bedrock IRSA
# -----------------------------------------------------------------------------
module "iam" {
  source = "../../modules/iam"

  name_prefix         = var.name_prefix
  oidc_provider_arn   = module.eks.oidc_provider_arn
  oidc_provider_url   = module.eks.oidc_provider_url

  datasets_bucket_arn = module.s3.datasets_bucket_arn
  reports_bucket_arn  = module.s3.reports_bucket_arn
  mlflow_bucket_arn   = module.s3.mlflow_bucket_arn
  s3_kms_key_arn      = module.s3.kms_key_arn

  secrets_manager_arns = [
    module.rds.secrets_manager_arn,
    module.elasticache.secrets_manager_arn,
  ]

  msk_cluster_arn = module.msk.cluster_arn

  tags = local.common_tags
}

module "bedrock_iam" {
  source = "../../modules/bedrock_iam"

  name_prefix        = var.name_prefix
  aws_region          = var.aws_region
  account_id          = var.account_id
  oidc_provider_arn   = module.eks.oidc_provider_arn
  oidc_provider_url   = module.eks.oidc_provider_url
  allowed_model_ids   = var.bedrock_model_ids
  enable_guardrails   = false

  tags = local.common_tags
}
