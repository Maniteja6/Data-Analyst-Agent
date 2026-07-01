# =============================================================================
# Shared remote state backend configuration
#
# This file is NOT applied directly — it documents the backend block each
# environment's main.tf must declare (Terraform does not support variables
# in backend blocks, so each environment hardcodes its own key path pointing
# at this shared bucket/table).
#
# Bootstrap once per AWS account, before running `terraform init` anywhere:
#
#   aws s3api create-bucket --bucket datapilot-terraform-state-<account-suffix> \
#     --region us-east-1
#   aws s3api put-bucket-versioning --bucket datapilot-terraform-state-<account-suffix> \
#     --versioning-configuration Status=Enabled
#   aws s3api put-bucket-encryption --bucket datapilot-terraform-state-<account-suffix> \
#     --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
#   aws dynamodb create-table --table-name datapilot-terraform-locks \
#     --attribute-definitions AttributeName=LockID,AttributeType=S \
#     --key-schema AttributeName=LockID,KeyType=HASH \
#     --billing-mode PAY_PER_REQUEST --region us-east-1
#
# Each environment/<env>/main.tf then declares:
#
#   terraform {
#     backend "s3" {
#       bucket         = "datapilot-terraform-state-<account-suffix>"
#       key            = "<env>/terraform.tfstate"
#       region         = "us-east-1"
#       dynamodb_table = "datapilot-terraform-locks"
#       encrypt        = true
#     }
#   }
# =============================================================================

# Optional: manage the state bucket and lock table themselves via Terraform,
# run once with a local backend before migrating to the S3 backend above.
# Left commented out by default to avoid chicken-and-egg apply ordering —
# uncomment and `terraform apply` with a local backend on first-time setup.

# resource "aws_s3_bucket" "terraform_state" {
#   bucket = "datapilot-terraform-state-${var.account_suffix}"
#
#   lifecycle {
#     prevent_destroy = true
#   }
# }
#
# resource "aws_s3_bucket_versioning" "terraform_state" {
#   bucket = aws_s3_bucket.terraform_state.id
#   versioning_configuration {
#     status = "Enabled"
#   }
# }
#
# resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
#   bucket = aws_s3_bucket.terraform_state.id
#   rule {
#     apply_server_side_encryption_by_default {
#       sse_algorithm = "AES256"
#     }
#   }
# }
#
# resource "aws_s3_bucket_public_access_block" "terraform_state" {
#   bucket                  = aws_s3_bucket.terraform_state.id
#   block_public_acls       = true
#   block_public_policy     = true
#   ignore_public_acls      = true
#   restrict_public_buckets = true
# }
#
# resource "aws_dynamodb_table" "terraform_locks" {
#   name         = "datapilot-terraform-locks"
#   billing_mode = "PAY_PER_REQUEST"
#   hash_key     = "LockID"
#
#   attribute {
#     name = "LockID"
#     type = "S"
#   }
#
#   lifecycle {
#     prevent_destroy = true
#   }
# }
