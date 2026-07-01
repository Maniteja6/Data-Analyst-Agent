output "db_instance_id" {
  value = aws_db_instance.this.id
}

output "db_address" {
  description = "RDS hostname (no port) — for application config that builds its own connection string"
  value       = aws_db_instance.this.address
}

output "db_endpoint" {
  description = "RDS endpoint including port"
  value       = aws_db_instance.this.endpoint
}

output "db_port" {
  value = aws_db_instance.this.port
}

output "database_name" {
  value = aws_db_instance.this.db_name
}

output "secrets_manager_arn" {
  description = "ARN of the Secrets Manager secret holding DB credentials — grant read access to the application's IAM role"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "security_group_id" {
  value = aws_security_group.rds.id
}
