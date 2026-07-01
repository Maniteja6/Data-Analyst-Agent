output "bucket_names" {
  description = "Map of logical bucket name -> actual S3 bucket name"
  value       = { for k, v in aws_s3_bucket.this : k => v.id }
}

output "bucket_arns" {
  description = "Map of logical bucket name -> bucket ARN"
  value       = { for k, v in aws_s3_bucket.this : k => v.arn }
}

output "datasets_bucket_name" {
  value = aws_s3_bucket.this["datasets"].id
}

output "datasets_bucket_arn" {
  value = aws_s3_bucket.this["datasets"].arn
}

output "reports_bucket_name" {
  value = aws_s3_bucket.this["reports"].id
}

output "reports_bucket_arn" {
  value = aws_s3_bucket.this["reports"].arn
}

output "mlflow_bucket_name" {
  value = aws_s3_bucket.this["mlflow"].id
}

output "mlflow_bucket_arn" {
  value = aws_s3_bucket.this["mlflow"].arn
}

output "kms_key_arn" {
  value = aws_kms_key.s3.arn
}
