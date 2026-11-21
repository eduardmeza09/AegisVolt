output "environment" { value = local.env }
output "namespace" { value = module.k8s_env.namespace }
output "vpc_id" { value = module.network.vpc_id }
output "vpc_cidr" { value = module.network.vpc_cidr }
output "vpc_endpoints" {
  value = merge(module.vpc_endpoints.gateway_endpoint_ids, module.vpc_endpoints.interface_endpoint_ids)
}
output "dynamodb_tables" {
  value = merge(module.dynamodb.table_names, { feature_flags = module.feature_flags.table_name })
}
output "log_groups" { value = module.observability.log_groups }
output "api_id" { value = module.api_gateway.api_id }
output "graphql_url" {
  description = "Endpoint GraphQL del ambiente (para el frontend)"
  value       = "${var.aws_endpoint}/restapis/${module.api_gateway.api_id}/${local.env}/_user_request_/graphql"
}
output "admin_token" {
  value     = random_password.admin_token.result
  sensitive = true
}
