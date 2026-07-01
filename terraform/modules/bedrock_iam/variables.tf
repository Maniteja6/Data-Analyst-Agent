variable "name_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "account_id" {
  description = "AWS account ID — required to build inference-profile and guardrail ARNs"
  type        = string
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
  description = "Kubernetes service accounts allowed to assume this role via IRSA — typically the API and worker pods that call Bedrock"
  type = list(object({
    namespace = string
    name      = string
  }))
  default = [
    { namespace = "datapilot", name = "datapilot-api" },
    { namespace = "datapilot", name = "datapilot-worker" },
  ]
}

variable "allowed_model_ids" {
  description = "Bedrock foundation model IDs the IRSA role may invoke directly (on-demand throughput)"
  type        = list(string)
  default = [
    "anthropic.claude-sonnet-4-5",
    "anthropic.claude-haiku-4-5",
    "amazon.titan-embed-text-v2:0",
  ]
}

variable "allowed_inference_profile_ids" {
  description = "Bedrock cross-region inference profile IDs the IRSA role may invoke (used when on-demand throughput requires a profile rather than a direct model ID)"
  type        = list(string)
  default     = []
}

variable "enable_guardrails" {
  description = "Whether to grant bedrock:ApplyGuardrail for content filtering on agent I/O"
  type        = bool
  default     = false
}

variable "guardrail_id" {
  description = "Bedrock Guardrail ID — required if enable_guardrails is true"
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
