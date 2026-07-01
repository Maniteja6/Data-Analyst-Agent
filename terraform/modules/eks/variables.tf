variable "name_prefix" {
  description = "Prefix applied to all resource names"
  type        = string
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS control plane"
  type        = string
  default     = "1.30"
}

variable "vpc_id" {
  description = "VPC ID to deploy the cluster into"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for nodes and control plane ENIs"
  type        = list(string)
}

variable "enable_public_endpoint" {
  description = "Whether the EKS API server endpoint is publicly reachable (restrict via public_access_cidrs)"
  type        = bool
  default     = true
}

variable "public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public EKS API endpoint"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "log_retention_days" {
  description = "CloudWatch log retention for EKS control plane logs"
  type        = number
  default     = 30
}

# Core node group (API, frontend, websocket gateway)
variable "core_instance_types" {
  type    = list(string)
  default = ["m6i.large"]
}

variable "core_desired_size" {
  type    = number
  default = 2
}

variable "core_min_size" {
  type    = number
  default = 2
}

variable "core_max_size" {
  type    = number
  default = 6
}

# Worker node group (Celery/Ray analytics workers, agent orchestrator)
variable "worker_instance_types" {
  type    = list(string)
  default = ["m6i.xlarge"]
}

variable "worker_capacity_type" {
  description = "ON_DEMAND or SPOT"
  type        = string
  default     = "ON_DEMAND"
}

variable "worker_desired_size" {
  type    = number
  default = 2
}

variable "worker_min_size" {
  type    = number
  default = 1
}

variable "worker_max_size" {
  type    = number
  default = 10
}

variable "tags" {
  type    = map(string)
  default = {}
}
