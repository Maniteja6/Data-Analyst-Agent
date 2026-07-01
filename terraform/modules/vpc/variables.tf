variable "name_prefix" {
  description = "Prefix applied to all resource names (e.g. 'datapilot-staging')"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name — used for required kubernetes.io subnet tags"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to span (3 recommended for production)"
  type        = number
  default     = 3
}

variable "single_nat_gateway" {
  description = "Use a single shared NAT gateway instead of one per AZ (saves cost in staging)"
  type        = bool
  default     = false
}

variable "enable_interface_endpoints" {
  description = "Create interface VPC endpoints for Bedrock, ECR, Secrets Manager (reduces NAT egress cost and latency)"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}
