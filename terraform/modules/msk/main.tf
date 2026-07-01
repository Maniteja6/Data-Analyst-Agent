# =============================================================================
# MSK Module — Managed Kafka for DataPilot's event-driven pipeline
#
# Backs all domain events: dataset.uploaded, analytics.completed,
# insight.report-generated, anomaly.detected, chat.message, agent.result.
# TLS-only client communication; IAM authentication used for app access
# (works cleanly with IRSA, no static SASL credentials to rotate).
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  common_tags = merge(var.tags, {
    Module    = "msk"
    ManagedBy = "terraform"
  })
}

resource "aws_security_group" "msk" {
  name        = "${var.name_prefix}-msk-sg"
  description = "Allow Kafka broker access from EKS nodes only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Kafka TLS broker port from EKS"
    from_port       = 9094
    to_port         = 9094
    protocol        = "tcp"
    security_groups = [var.eks_cluster_security_group_id]
  }

  ingress {
    description     = "Kafka IAM-auth broker port from EKS"
    from_port       = 9098
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [var.eks_cluster_security_group_id]
  }

  ingress {
    description     = "Zookeeper / Kafka internal from EKS (Schema Registry, kafka-ui tooling)"
    from_port       = 2181
    to_port         = 2181
    protocol        = "tcp"
    security_groups = [var.eks_cluster_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-msk-sg" })
}

resource "aws_kms_key" "msk" {
  description             = "KMS key for ${var.name_prefix} MSK encryption at rest"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = local.common_tags
}

resource "aws_cloudwatch_log_group" "msk_broker_logs" {
  name              = "/aws/msk/${var.name_prefix}/broker-logs"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_msk_configuration" "this" {
  name              = "${var.name_prefix}-msk-config"
  kafka_versions    = [var.kafka_version]
  server_properties = <<-PROPERTIES
    auto.create.topics.enable=false
    default.replication.factor=${var.broker_count >= 3 ? 3 : var.broker_count}
    min.insync.replicas=${var.broker_count >= 3 ? 2 : 1}
    num.partitions=6
    log.retention.hours=168
    log.retention.bytes=-1
    compression.type=producer
  PROPERTIES
}

resource "aws_msk_cluster" "this" {
  cluster_name           = "${var.name_prefix}-kafka"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.broker_count

  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.broker_ebs_volume_gb
      }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.this.arn
    revision = aws_msk_configuration.this.latest_revision
  }

  encryption_info {
    encryption_at_rest_kms_key_arn = aws_kms_key.msk.arn
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  client_authentication {
    tls {}
    sasl {
      iam = true # IAM auth — pairs cleanly with IRSA, no rotated secrets needed
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk_broker_logs.name
      }
    }
  }

  enhanced_monitoring = var.enhanced_monitoring

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-kafka" })
}

# -----------------------------------------------------------------------------
# Glue Schema Registry — Avro schema enforcement for domain events
# (Confluent Schema Registry can be run in-cluster instead; this is the
# managed-AWS alternative referenced by the architecture doc)
# -----------------------------------------------------------------------------
resource "aws_glue_registry" "this" {
  registry_name = "${var.name_prefix}-event-schemas"
  description   = "Avro schema registry for DataPilot domain events"
  tags          = local.common_tags
}
