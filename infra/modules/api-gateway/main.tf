# Entrada pública: API Gateway HTTP API (v2) por ambiente.
#
# Camino en AWS real (integration_mode = "vpc_link"):
#   Cliente -> API GW -> VPC Link (ENIs en subredes privadas del ambiente) -> NLB interno
#   -> peering -> NodePort Traefik (30080) en los nodos EKS -> IngressRoute /<env>/graphql-gateway -> pod gateway
#
# En Floci 2.4.0 el plano de datos de VPC Link no está emulado (sí el control plane), por lo que
# integration_mode = "direct" usa HTTP_PROXY al NodePort del nodo k3s (misma red privada Docker).
# Los recursos VPC Link / NLB se declaran igual para que la topología quede como código.

variable "env" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "vpce_security_group_id" { type = string }
variable "node_ip" { type = string }
variable "node_port" {
  type    = number
  default = 30080
}
variable "integration_mode" {
  type    = string
  default = "direct"
  validation {
    condition     = contains(["direct", "vpc_link"], var.integration_mode)
    error_message = "integration_mode debe ser direct o vpc_link"
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_lb" "ingress" {
  name               = "aegisvolt-${var.env}-nlb"
  internal           = true
  load_balancer_type = "network"
  subnets            = var.private_subnet_ids
  tags               = var.tags
}

resource "aws_lb_target_group" "traefik" {
  name        = "aegisvolt-${var.env}-traefik"
  port        = var.node_port
  protocol    = "TCP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    protocol = "HTTP"
    port     = tostring(var.node_port)
    path     = "/${var.env}/graphql-gateway/healthz"
    matcher  = "200"
  }
  tags = var.tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.ingress.arn
  port              = 80
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.traefik.arn
  }
}

resource "aws_apigatewayv2_vpc_link" "this" {
  name               = "aegisvolt-${var.env}-vpclink"
  subnet_ids         = var.private_subnet_ids
  security_group_ids = [var.vpce_security_group_id]
  tags               = var.tags
}

resource "aws_apigatewayv2_api" "this" {
  name          = "aegisvolt-${var.env}-api"
  protocol_type = "HTTP"
  description   = "AegisVolt GraphQL (${var.env})"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "gateway" {
  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri = (var.integration_mode == "vpc_link"
    ? aws_lb_listener.http.arn
  : "http://${var.node_ip}:${var.node_port}/${var.env}/graphql-gateway/{proxy}")
  connection_type        = var.integration_mode == "vpc_link" ? "VPC_LINK" : "INTERNET"
  connection_id          = var.integration_mode == "vpc_link" ? aws_apigatewayv2_vpc_link.this.id : null
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.gateway.id}"
}

# Frontend (nginx en el namespace del ambiente) bajo el MISMO API: .../<stage>/web/
# => el navegador habla con GraphQL en el mismo origen (.../<stage>/graphql), sin CORS.
resource "aws_apigatewayv2_integration" "frontend" {
  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri = (var.integration_mode == "vpc_link"
    ? aws_lb_listener.http.arn
  : "http://${var.node_ip}:${var.node_port}/${var.env}/web/{proxy}")
  connection_type        = var.integration_mode == "vpc_link" ? "VPC_LINK" : "INTERNET"
  connection_id          = var.integration_mode == "vpc_link" ? aws_apigatewayv2_vpc_link.this.id : null
  payload_format_version = "1.0"
}

# {proxy+} exige al menos un segmento: la raíz /web y /web/ necesitan su propia ruta.
resource "aws_apigatewayv2_integration" "frontend_root" {
  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri = (var.integration_mode == "vpc_link"
    ? aws_lb_listener.http.arn
  : "http://${var.node_ip}:${var.node_port}/${var.env}/web/")
  connection_type        = var.integration_mode == "vpc_link" ? "VPC_LINK" : "INTERNET"
  connection_id          = var.integration_mode == "vpc_link" ? aws_apigatewayv2_vpc_link.this.id : null
  payload_format_version = "1.0"
}

resource "aws_apigatewayv2_route" "frontend_root" {
  for_each  = toset(["ANY /web", "ANY /web/"])
  api_id    = aws_apigatewayv2_api.this.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.frontend_root.id}"
}

resource "aws_apigatewayv2_route" "frontend" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /web/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.frontend.id}"
}

resource "aws_apigatewayv2_stage" "env" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = var.env
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 200
    throttling_rate_limit  = 100
  }
  tags = var.tags
}

output "api_id" { value = aws_apigatewayv2_api.this.id }
output "stage" { value = aws_apigatewayv2_stage.env.name }
output "vpc_link_id" { value = aws_apigatewayv2_vpc_link.this.id }
output "nlb_arn" { value = aws_lb.ingress.arn }
