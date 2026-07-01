# =============================================================================
# ElastiCache Module — Redis for DataPilot
#
# Backs: LLM response cache, session state, working memory buffer,
# Celery broker/result backend, WebSocket pub/sub fan-out, rate limiting.
# Deployed as a replication group with automatic failover for production.
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

locals {
  common_tags = merge(var.tags, {
    Module    = "elasticache"
    ManagedBy = "terraform"
  })
}

resource "random_password" "auth_token" {
  length  = 64
  special = false # ElastiCache AUTH tokens disallow many special characters
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis-subnet-group"
  subnet_ids = var.private_subnet_ids
  tags       = local.common_tags
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Allow Redis access from EKS nodes only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from EKS cluster security group"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.eks_cluster_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-redis-sg" })
}

resource "aws_elasticache_parameter_group" "this" {
  name   = "${var.name_prefix}-redis7-params"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru" # evict least-recently-used keys — appropriate for cache + session data
  }

  tags = local.common_tags
}

resource "aws_kms_key" "redis" {
  description             = "KMS key for ${var.name_prefix} Redis encryption at rest"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = local.common_tags
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name_prefix}-redis"
  description           = "DataPilot Redis — cache, sessions, Celery broker, pub/sub"

  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  port                 = 6379

  parameter_group_name = aws_elasticache_parameter_group.this.name
  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = [aws_security_group.redis.id]

  num_node_groups         = var.num_shards
  replicas_per_node_group = var.replicas_per_shard

  automatic_failover_enabled = var.num_shards > 0 && var.replicas_per_shard > 0
  multi_az_enabled           = var.multi_az

  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.redis.arn
  transit_encryption_enabled = true
  auth_token                 = random_password.auth_token.result

  snapshot_retention_limit = var.snapshot_retention_days
  snapshot_window          = "05:00-06:00"
  maintenance_window       = "mon:06:30-mon:07:30"

  auto_minor_version_upgrade = true

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-redis" })
}

# -----------------------------------------------------------------------------
# Secrets Manager — auth token + connection details
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "redis_credentials" {
  name                    = "${var.name_prefix}/elasticache/redis-credentials"
  recovery_window_in_days = 7
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "redis_credentials" {
  secret_id = aws_secretsmanager_secret.redis_credentials.id
  secret_string = jsonencode({
    auth_token       = random_password.auth_token.result
    primary_endpoint = aws_elasticache_replication_group.this.primary_endpoint_address
    reader_endpoint  = aws_elasticache_replication_group.this.reader_endpoint_address
    port             = 6379
    url              = "rediss://:${random_password.auth_token.result}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
  })
}
