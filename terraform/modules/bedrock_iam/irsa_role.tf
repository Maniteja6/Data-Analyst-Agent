# =============================================================================
# IRSA helper outputs — the Kubernetes-side annotation snippet
#
# Split from main.tf to keep the IRSA trust relationship and the resulting
# Kubernetes wiring instructions easy to find independently; main.tf owns the
# IAM resources, this file documents/derives what the cluster side needs.
# =============================================================================

# Renders the exact annotation block a Helm values.yaml or ServiceAccount
# manifest needs in order to assume this role. Surfaced as an output so
# deploy/helm/datapilot/templates/service-account.yaml can reference it
# directly (e.g. via -var or a generated values file) instead of hand-typing
# the role ARN in two places.
locals {
  service_account_annotation = {
    "eks.amazonaws.com/role-arn" = aws_iam_role.bedrock_irsa.arn
  }
}

output "service_account_annotation" {
  description = "Annotation map to apply to the Kubernetes ServiceAccount so pods can assume the Bedrock IRSA role"
  value       = local.service_account_annotation
}
