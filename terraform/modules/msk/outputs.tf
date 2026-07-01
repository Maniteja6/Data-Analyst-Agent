output "cluster_arn" {
  value = aws_msk_cluster.this.arn
}

output "bootstrap_brokers_tls" {
  description = "TLS broker connection string for clients using TLS client auth"
  value       = aws_msk_cluster.this.bootstrap_brokers_tls
}

output "bootstrap_brokers_sasl_iam" {
  description = "IAM-auth broker connection string — preferred for IRSA-based pod access"
  value       = aws_msk_cluster.this.bootstrap_brokers_sasl_iam
}

output "zookeeper_connect_string" {
  value = aws_msk_cluster.this.zookeeper_connect_string
}

output "security_group_id" {
  value = aws_security_group.msk.id
}

output "glue_registry_arn" {
  description = "ARN of the Glue Schema Registry for Avro event schemas"
  value       = aws_glue_registry.this.arn
}

output "glue_registry_name" {
  value = aws_glue_registry.this.registry_name
}
