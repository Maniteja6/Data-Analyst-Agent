output "app_role_arn" {
  description = "IAM role ARN to annotate on the Kubernetes service account (eks.amazonaws.com/role-arn)"
  value       = aws_iam_role.app.arn
}

output "app_role_name" {
  value = aws_iam_role.app.name
}
