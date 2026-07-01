variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "account_id" {
  description = "AWS account ID — required for Bedrock inference profile / guardrail ARNs"
  type        = string
}

variable "account_suffix" {
  description = "Short unique suffix for globally-unique resource names (e.g. last 6 digits of account ID)"
  type        = string
}

variable "environment" {
  type    = string
  default = "production"
}

variable "name_prefix" {
  type    = string
  default = "datapilot-prod"
}

variable "cluster_name" {
  type    = string
  default = "datapilot-prod"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "kubernetes_version" {
  type    = string
  default = "1.30"
}

variable "public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public EKS API endpoint — restrict to office/VPN/bastion in production"
  type        = list(string)
  default     = []  # intentionally empty; must be explicitly set in production tfvars
}

variable "cors_allowed_origins" {
  description = "Frontend origins allowed to upload directly to the datasets S3 bucket"
  type        = list(string)
  default     = ["https://app.datapilot.example.com"]
}

variable "bedrock_model_ids" {
  type = list(string)
  default = [
    "anthropic.claude-sonnet-4-5",
    "anthropic.claude-haiku-4-5",
    "amazon.titan-embed-text-v2:0",
  ]
}

variable "bedrock_enable_guardrails" {
  type    = bool
  default = true
}

variable "bedrock_guardrail_id" {
  description = "Bedrock Guardrail ID applied to production agent I/O (PII, content filters)"
  type        = string
  default     = ""
}

variable "tags" {
  type = map(string)
  default = {
    Project = "datapilot"
  }
}
