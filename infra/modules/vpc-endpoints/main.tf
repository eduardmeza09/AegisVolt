# VPC Endpoints: el tráfico privado hacia los servicios AWS NO sale a internet.
#  - Gateway (S3, DynamoDB): se inyectan como rutas (prefix list) en la tabla de ruta privada.
#  - Interface (execute-api, logs, monitoring, sts): ENIs en las subredes privadas, con
#    private DNS => el FQDN público del servicio resuelve a IPs privadas de la VPC.

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "vpc_cidr" { type = string }
variable "region" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "private_route_table_ids" { type = list(string) }
variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  gateway   = ["s3", "dynamodb"]
  interface = ["execute-api", "logs", "monitoring", "sts"]
}

resource "aws_security_group" "vpce" {
  name        = "${var.name}-vpce"
  description = "Interface VPC endpoints: HTTPS solo desde la propia VPC"
  vpc_id      = var.vpc_id
  ingress {
    description = "HTTPS desde la VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
  tags = var.tags
}

resource "aws_vpc_endpoint" "gateway" {
  for_each          = toset(local.gateway)
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids
  tags              = merge(var.tags, { Name = "${var.name}-vpce-${each.key}" })
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = toset(local.interface)
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpce.id]
  private_dns_enabled = true
  tags                = merge(var.tags, { Name = "${var.name}-vpce-${each.key}" })
}

output "gateway_endpoint_ids" { value = { for k, v in aws_vpc_endpoint.gateway : k => v.id } }
output "interface_endpoint_ids" { value = { for k, v in aws_vpc_endpoint.interface : k => v.id } }
output "execute_api_vpce_id" { value = aws_vpc_endpoint.interface["execute-api"].id }
output "vpce_security_group_id" { value = aws_security_group.vpce.id }
