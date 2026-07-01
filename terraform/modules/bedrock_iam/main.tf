# =============================================================================
# Bedrock IAM Module — IRSA role granting DataPilot pods access to AWS Bedrock
#
# Scoped specifically to the model ARNs DataPilot uses (Claude Sonnet/Haiku
# for reasoning, Titan Embeddings for RAG) rather than a wildcard grant.
# Kept separate from the general app IAM module so LLM access is auditable
# in isolation — this is the policy security reviewers will look at first.
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  common_tags = merge(var.tags, {
    Module    = "bedrock_iam"
    ManagedBy = "terraform"
  })

  oidc_sub_condition_values = [
    for sa in var.service_accounts : "system:serviceaccount:${sa.namespace}:${sa.name}"
  ]

  # Foundation model ARNs are region-scoped and account-agnostic (no account ID in ARN)
  model_arns = [
    for model_id in var.allowed_model_ids :
    "arn:aws:bedrock:${var.aws_region}::foundation-model/${model_id}"
  ]

  # Cross-region inference profile ARNs (account-scoped) — required when using
  # Claude's inference profile IDs (e.g. "us.anthropic.claude-sonnet-4-5") instead
  # of direct on-demand foundation-model IDs
  inference_profile_arns = [
    for profile_id in var.allowed_inference_profile_ids :
    "arn:aws:bedrock:${var.aws_region}:${var.account_id}:inference-profile/${profile_id}"
  ]
}

data "aws_iam_policy_document" "irsa_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${var.oidc_provider_url}:sub"
      values   = local.oidc_sub_condition_values
    }
  }
}

resource "aws_iam_role" "bedrock_irsa" {
  name               = "${var.name_prefix}-bedrock-irsa-role"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume.json
  tags               = local.common_tags
}

# -----------------------------------------------------------------------------
# Bedrock invoke policy — rendered from the bedrock_invoke_policy.json template
# with model ARNs injected, rather than a static wildcard file
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "InvokeAllowedModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = concat(local.model_arns, local.inference_profile_arns)
  }

  statement {
    sid       = "ListAndDescribeModels"
    effect    = "Allow"
    actions   = ["bedrock:ListFoundationModels", "bedrock:GetFoundationModel"]
    resources = ["*"] # read-only metadata calls; not scopable to specific ARNs
  }

  dynamic "statement" {
    for_each = var.enable_guardrails ? [1] : []
    content {
      sid       = "ApplyGuardrails"
      effect    = "Allow"
      actions   = ["bedrock:ApplyGuardrail"]
      resources = ["arn:aws:bedrock:${var.aws_region}:${var.account_id}:guardrail/${var.guardrail_id}"]
    }
  }
}

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "${var.name_prefix}-bedrock-invoke-policy"
  description = "Scoped Bedrock InvokeModel access for DataPilot agents (Claude Sonnet/Haiku, Titan Embeddings)"
  policy      = data.aws_iam_policy_document.bedrock_invoke.json
  tags        = local.common_tags
}

resource "aws_iam_role_policy_attachment" "bedrock_invoke" {
  role       = aws_iam_role.bedrock_irsa.name
  policy_arn = aws_iam_policy.bedrock_invoke.arn
}

# -----------------------------------------------------------------------------
# CloudWatch — allow the cost tracker / token tracker to publish custom metrics
# (datapilot_llm_tokens_total, datapilot_llm_cost_usd_total)
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "bedrock_metrics" {
  statement {
    sid    = "PublishCustomMetrics"
    effect = "Allow"
    actions = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DataPilot/Bedrock"]
    }
  }
}

resource "aws_iam_policy" "bedrock_metrics" {
  name   = "${var.name_prefix}-bedrock-metrics-policy"
  policy = data.aws_iam_policy_document.bedrock_metrics.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "bedrock_metrics" {
  role       = aws_iam_role.bedrock_irsa.name
  policy_arn = aws_iam_policy.bedrock_metrics.arn
}
