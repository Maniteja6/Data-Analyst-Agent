# =============================================================================
# S3 Module — Object storage for DataPilot
#
# Three buckets:
#   - datasets  — uploaded user files, accessed via short-lived presigned URLs
#   - reports   — generated PDF/PPTX/XLSX exports
#   - mlflow    — MLflow artifact store for trained forecast/ML models
# All buckets are private, encrypted, versioned, and have lifecycle rules
# to control storage cost over time.
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
    Module    = "s3"
    ManagedBy = "terraform"
  })

  buckets = {
    datasets = {
      name        = "${var.name_prefix}-datasets-${var.account_suffix}"
      description = "Uploaded user datasets (CSV/XLSX/Parquet/JSON)"
    }
    reports = {
      name        = "${var.name_prefix}-reports-${var.account_suffix}"
      description = "Generated PDF/PPTX/XLSX export reports"
    }
    mlflow = {
      name        = "${var.name_prefix}-mlflow-${var.account_suffix}"
      description = "MLflow artifact store for trained models"
    }
  }
}

resource "aws_kms_key" "s3" {
  description             = "KMS key for ${var.name_prefix} S3 bucket encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = local.common_tags
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket = each.value.name
  tags   = merge(local.common_tags, { Name = each.value.name, Description = each.value.description })
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

# -----------------------------------------------------------------------------
# Lifecycle rules
#   - datasets: move to Infrequent Access after 30 days, expire temp/ after 7 days
#   - reports:  expire after 90 days (regenerable from source data)
#   - mlflow:   keep indefinitely, but transition old versions to IA
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_lifecycle_configuration" "datasets" {
  bucket = aws_s3_bucket.this["datasets"].id

  rule {
    id     = "expire-temp-uploads"
    status = "Enabled"
    filter { prefix = "tmp/" }
    expiration { days = 7 }
  }

  rule {
    id     = "transition-datasets-to-ia"
    status = "Enabled"
    filter { prefix = "datasets/" }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    noncurrent_version_expiration { noncurrent_days = 90 }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.this["reports"].id

  rule {
    id     = "expire-old-reports"
    status = "Enabled"
    filter { prefix = "reports/" }
    expiration { days = 90 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "mlflow" {
  bucket = aws_s3_bucket.this["mlflow"].id

  rule {
    id     = "transition-old-model-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_transition {
      noncurrent_days = 60
      storage_class   = "STANDARD_IA"
    }
  }
}

# -----------------------------------------------------------------------------
# CORS — required for the frontend to issue direct presigned-URL uploads
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_cors_configuration" "datasets" {
  bucket = aws_s3_bucket.this["datasets"].id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# -----------------------------------------------------------------------------
# Bucket policy — deny any non-TLS request
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "deny_insecure_transport" {
  for_each = local.buckets

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.this[each.key].arn,
      "${aws_s3_bucket.this[each.key].arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  policy = data.aws_iam_policy_document.deny_insecure_transport[each.key].json
}
