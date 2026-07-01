# =============================================================================
# Shared provider version constraints
#
# Symlinked or copy-pasted into each environment's main.tf via the
# `terraform { required_providers { ... } }` block — kept here as the single
# source of truth for which provider versions the whole project is tested
# against. Bump versions here first, then propagate to environments.
# =============================================================================

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.31"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.14"
    }
  }
}

# -----------------------------------------------------------------------------
# Default tags applied to every resource created by the aws provider —
# environments instantiate their own `provider "aws"` block (region differs
# per environment) but should include this default_tags configuration.
# -----------------------------------------------------------------------------
# provider "aws" {
#   region = var.aws_region
#
#   default_tags {
#     tags = {
#       Project     = "datapilot"
#       Environment = var.environment
#       ManagedBy   = "terraform"
#     }
#   }
# }
