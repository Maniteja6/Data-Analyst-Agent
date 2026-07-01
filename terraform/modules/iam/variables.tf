variable "name_prefix" {
  type = string
}

variable "oidc_provider_arn" {
  description = "ARN of the EKS OIDC provider (from the eks module output)"
  type        = string
}

variable "oidc_provider_url" {
  description = "OIDC provider URL without https:// prefix (from the eks module output)"
  type        = string
}

variable "service_accounts" {
  description = "Kubernetes service accounts allowed to assume this role via IRSA"
  type = list(object({
    namespace = string
    name      = string
  }))
  default = [
    { namespace = "datapilot", name = "datapilot-api" },
    { namespace = "datapilot", name = "datapilot-worker" },
    { namespace = "datapilot", name = "datapilot-analytics" },
  ]
}

variable "datasets_bucket_arn" {
  type = string
}

variable "reports_bucket_arn" {
  type = string
}

variable "mlflow_bucket_arn" {
  type = string
}

variable "s3_kms_key_arn" {
  type = string
}

variable "secrets_manager_arns" {
  description = "ARNs of Secrets Manager secrets the app role is allowed to read (RDS, Redis credentials)"
  type        = list(string)
}

variable "msk_cluster_arn" {
  description = "ARN of the MSK cluster — set to null to skip granting Kafka IAM-auth access"
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
