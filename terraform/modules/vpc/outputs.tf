output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of public subnets (one per AZ)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of private subnets (one per AZ) — used by EKS nodes, RDS, ElastiCache, MSK"
  value       = aws_subnet.private[*].id
}

output "availability_zones" {
  description = "Availability zones used"
  value       = local.azs
}

output "nat_gateway_ids" {
  description = "IDs of NAT gateways"
  value       = aws_nat_gateway.this[*].id
}

output "vpc_endpoints_security_group_id" {
  description = "Security group ID attached to interface VPC endpoints"
  value       = var.enable_interface_endpoints ? aws_security_group.vpc_endpoints[0].id : null
}
