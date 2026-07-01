variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "eks_cluster_security_group_id" {
  description = "Security group of the EKS cluster, used to scope RDS ingress"
  type        = string
}

variable "engine_version" {
  type    = string
  default = "16.4"
}

variable "instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "allocated_storage_gb" {
  type    = number
  default = 100
}

variable "max_allocated_storage_gb" {
  description = "Upper bound for RDS storage autoscaling"
  type        = number
  default     = 500
}

variable "database_name" {
  type    = string
  default = "datapilot"
}

variable "master_username" {
  type    = string
  default = "datapilot_admin"
}

variable "multi_az" {
  description = "Enable Multi-AZ standby (recommended for production)"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  type    = number
  default = 14
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
