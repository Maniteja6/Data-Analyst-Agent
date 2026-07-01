output "primary_endpoint_address" {
  value = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "reader_endpoint_address" {
  value = aws_elasticache_replication_group.this.reader_endpoint_address
}

output "port" {
  value = 6379
}

output "secrets_manager_arn" {
  description = "ARN of the Secrets Manager secret holding the Redis AUTH token and connection URL"
  value       = aws_secretsmanager_secret.redis_credentials.arn
}

output "security_group_id" {
  value = aws_security_group.redis.id
}
