variable "name_prefix" {
  type = string
}

variable "account_suffix" {
  description = "Short unique suffix (e.g. AWS account ID last 6 digits) to guarantee global bucket name uniqueness"
  type        = string
}

variable "cors_allowed_origins" {
  description = "Origins allowed to issue CORS requests against the datasets bucket (frontend URLs)"
  type        = list(string)
  default     = ["http://localhost:3000"]
}

variable "tags" {
  type    = map(string)
  default = {}
}
