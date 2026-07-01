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
  type = string
}

variable "kafka_version" {
  type    = string
  default = "3.7.x"
}

variable "broker_count" {
  description = "Total broker count across AZs (must be a multiple of subnet count; 3 recommended for production)"
  type        = number
  default     = 3
}

variable "broker_instance_type" {
  type    = string
  default = "kafka.m5.large"
}

variable "broker_ebs_volume_gb" {
  type    = number
  default = 200
}

variable "enhanced_monitoring" {
  description = "DEFAULT, PER_BROKER, PER_TOPIC_PER_BROKER, or PER_TOPIC_PER_PARTITION"
  type        = string
  default     = "PER_TOPIC_PER_BROKER"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "tags" {
  type    = map(string)
  default = {}
}
