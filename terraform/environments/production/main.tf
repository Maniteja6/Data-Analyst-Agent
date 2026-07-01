# =============================================================================
# DataPilot — Production Environment
#
# Multi-AZ everywhere, Multi-AZ RDS standby, Redis replica with automatic
# failover, 3-broker MSK cluster, on-demand EKS worker capacity, deletion
# protection enabled, and Bedrock Guardrails applied to agent I/O.
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
    key            = "production/terraform.tfstate"
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
  az_count                    = 3     # full 3-AZ spread for production resilience
  single_nat_gateway          = false # one NAT per AZ — avoids cross-AZ data transfer + single point of failure
  enable_interface_endpoints  = true  # Bedrock/ECR/Secrets Manager traffic stays off public internet
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
  public_access_cidrs    = var.public_access_cidrs # must be set explicitly — no public default in production
  core_instance_types = ["m6i.large", "m6i.xlarge"]
  core_desired_size   = 3
  core_min_size       = 3
  core_max_size       = 10

  worker_instance_types = ["m6i.xlarge", "m6i.2xlarge"]
  worker_capacity_type  = "ON_DEMAND" # production workers use on-demand for predictable analytics latency
  worker_desired_size   = 3
  worker_min_size       = 2
  worker_max_size       = 20

  log_retention_days = 90
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

  instance_class           = "db.r6g.xlarge"
  allocated_storage_gb     = 200
  max_allocated_storage_gb = 1000
  multi_az                 = true
  backup_retention_days    = 30
  deletion_protection      = true

  tags = local.common_tags
}

module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix                    = var.name_prefix
  vpc_id                         = module.vpc.vpc_id
  private_subnet_ids             = module.vpc.private_subnet_ids
  eks_cluster_security_group_id  = module.eks.cluster_security_group_id

  node_type           = "cache.r6g.xlarge"
  num_shards          = 2
  replicas_per_shard  = 1
  multi_az            = true

  tags = local.common_tags
}

module "msk" {
  source = "../../modules/msk"

  name_prefix                    = var.name_prefix
  vpc_id                         = module.vpc.vpc_id
  private_subnet_ids             = module.vpc.private_subnet_ids
  eks_cluster_security_group_id  = module.eks.cluster_security_group_id

  broker_count          = 3
  broker_instance_type  = "kafka.m5.large"
  broker_ebs_volume_gb  = 500
  enhanced_monitoring   = "PER_TOPIC_PER_BROKER"

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
  enable_guardrails   = var.bedrock_enable_guardrails
  guardrail_id        = var.bedrock_guardrail_id

  tags = local.common_tags
}
