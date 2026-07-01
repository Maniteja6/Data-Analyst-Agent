# =============================================================================
# IAM Module — Application-level IRSA roles (non-Bedrock)
#
# Bedrock access is handled separately in modules/bedrock_iam to keep LLM
# permissions auditable in isolation. This module covers the other IRSA
# roles application pods need: S3 (datasets/reports/mlflow buckets),
# Secrets Manager (RDS/Redis credentials), and MSK (IAM-auth Kafka access).
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
    Module    = "iam"
    ManagedBy = "terraform"
  })

  # IRSA trust condition is identical across all app roles in this module
  oidc_sub_condition_values = [for sa in var.service_accounts : "system:serviceaccount:${sa.namespace}:${sa.name}"]
}

# -----------------------------------------------------------------------------
# Trust policy shared by all application IRSA roles
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "irsa_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${var.oidc_provider_url}:sub"
      values   = local.oidc_sub_condition_values
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${var.name_prefix}-app-role"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume.json
  tags               = local.common_tags
}

# -----------------------------------------------------------------------------
# S3 access — datasets (read/write), reports (read/write), mlflow (read/write)
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "s3_access" {
  statement {
    sid     = "DatasetReadWrite"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [
      var.datasets_bucket_arn,
      "${var.datasets_bucket_arn}/*",
      var.reports_bucket_arn,
      "${var.reports_bucket_arn}/*",
      var.mlflow_bucket_arn,
      "${var.mlflow_bucket_arn}/*",
    ]
  }

  statement {
    sid       = "KMSDecryptEncrypt"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.s3_kms_key_arn]
  }
}

resource "aws_iam_policy" "s3_access" {
  name   = "${var.name_prefix}-s3-access-policy"
  policy = data.aws_iam_policy_document.s3_access.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "s3_access" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.s3_access.arn
}

# -----------------------------------------------------------------------------
# Secrets Manager — read DB and Redis credentials at pod startup
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "secrets_access" {
  statement {
    sid       = "ReadAppSecrets"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = var.secrets_manager_arns
  }
}

resource "aws_iam_policy" "secrets_access" {
  name   = "${var.name_prefix}-secrets-access-policy"
  policy = data.aws_iam_policy_document.secrets_access.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "secrets_access" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.secrets_access.arn
}

# -----------------------------------------------------------------------------
# MSK — IAM-auth Kafka producer/consumer access for application pods
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "msk_access" {
  statement {
    sid    = "MSKClusterConnect"
    effect = "Allow"
    actions = [
      "kafka-cluster:Connect",
      "kafka-cluster:AlterCluster",
      "kafka-cluster:DescribeCluster",
    ]
    resources = [var.msk_cluster_arn]
  }

  statement {
    sid    = "MSKTopicReadWrite"
    effect = "Allow"
    actions = [
      "kafka-cluster:*Topic*",
      "kafka-cluster:WriteData",
      "kafka-cluster:ReadData",
    ]
    resources = ["${replace(var.msk_cluster_arn, ":cluster/", ":topic/")}/*"]
  }

  statement {
    sid    = "MSKConsumerGroup"
    effect = "Allow"
    actions = [
      "kafka-cluster:AlterGroup",
      "kafka-cluster:DescribeGroup",
    ]
    resources = ["${replace(var.msk_cluster_arn, ":cluster/", ":group/")}/*"]
  }
}

resource "aws_iam_policy" "msk_access" {
  count  = var.msk_cluster_arn != null ? 1 : 0
  name   = "${var.name_prefix}-msk-access-policy"
  policy = data.aws_iam_policy_document.msk_access.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "msk_access" {
  count      = var.msk_cluster_arn != null ? 1 : 0
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.msk_access[0].arn
}
