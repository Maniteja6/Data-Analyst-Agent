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

variable "engine_version" {
  type    = string
  default = "7.1"
}

variable "node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "num_shards" {
  description = "Number of shards (node groups) for cluster-mode. 1 disables cluster-mode sharding."
  type        = number
  default     = 1
}

variable "replicas_per_shard" {
  description = "Replica count per shard — set to 0 in staging to save cost, >=1 in production for failover"
  type        = number
  default     = 1
}

variable "multi_az" {
  type    = bool
  default = true
}

variable "snapshot_retention_days" {
  type    = number
  default = 7
}

variable "tags" {
  type    = map(string)
  default = {}
}
