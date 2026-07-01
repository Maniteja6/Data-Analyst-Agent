output "role_arn" {
  description = "IAM role ARN for Bedrock access — annotate the Kubernetes service account with this"
  value       = aws_iam_role.bedrock_irsa.arn
}

output "role_name" {
  value = aws_iam_role.bedrock_irsa.name
}

output "policy_arn" {
  description = "ARN of the scoped Bedrock InvokeModel policy"
  value       = aws_iam_policy.bedrock_invoke.arn
}

output "allowed_model_arns" {
  description = "Full list of foundation-model ARNs this role may invoke"
  value       = local.model_arns
}
