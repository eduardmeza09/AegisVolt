# Stack por ambiente. Uso:  terraform workspace select dev|test|prod && terraform apply

# Guardián: impide aplicar en el workspace "default" o en uno desconocido.
resource "terraform_data" "workspace_guard" {
  input = local.env
  lifecycle {
    precondition {
      condition     = contains(["dev", "test", "prod"], terraform.workspace)
      error_message = "Workspace '${terraform.workspace}' inválido. Usa: terraform workspace select dev|test|prod"
    }
  }
}

data "terraform_remote_state" "platform" {
  backend = "s3"
  config = {
    bucket                      = "aegisvolt-tfstate"
    key                         = "platform/terraform.tfstate"
    region                      = "us-east-1"
    access_key                  = "test"
    secret_key                  = "test"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    use_path_style              = true
    endpoints                   = { s3 = "http://localhost:4566", sts = "http://localhost:4566" }
  }
}

locals {
  platform = data.terraform_remote_state.platform.outputs
}

# ------------------------------------------------------------------- red del ambiente
module "network" {
  source = "../modules/network"
  name   = "aegisvolt-${local.env}"
  cidr   = local.cfg.cidr
  azs    = local.azs
  tags   = local.tags
}

module "vpc_endpoints" {
  source                  = "../modules/vpc-endpoints"
  name                    = "aegisvolt-${local.env}"
  vpc_id                  = module.network.vpc_id
  vpc_cidr                = module.network.vpc_cidr
  region                  = local.region
  private_subnet_ids      = module.network.private_subnet_ids
  private_route_table_ids = [module.network.private_route_table_id]
  tags                    = local.tags
}

# Peering VPC del ambiente <-> VPC de plataforma (donde corre EKS): el NLB/VPC Link del
# ambiente alcanza los nodos por rutas privadas, sin pasar por internet.
resource "aws_vpc_peering_connection" "to_platform" {
  vpc_id      = module.network.vpc_id
  peer_vpc_id = local.platform.platform_vpc_id
  auto_accept = true
  tags        = merge(local.tags, { Name = "aegisvolt-${local.env}-to-platform" })
}

resource "aws_route" "env_to_platform" {
  route_table_id            = module.network.private_route_table_id
  destination_cidr_block    = local.platform.platform_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.to_platform.id
}

resource "aws_route" "platform_to_env" {
  route_table_id            = local.platform.platform_private_route_table_id
  destination_cidr_block    = local.cfg.cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.to_platform.id
}

# ---------------------------------------------------------------------------- datos
module "dynamodb" {
  source                 = "../modules/dynamodb"
  env                    = local.env
  point_in_time_recovery = local.cfg.pitr
  tags                   = local.tags
}

module "feature_flags" {
  source = "../modules/feature-flags"
  env    = local.env
  flags  = local.cfg.flags
  tags   = local.tags
}

# --------------------------------------------------------------------- observabilidad
module "observability" {
  source                = "../modules/observability"
  env                   = local.env
  services              = local.services
  retention_days        = local.cfg.log_retention
  error_alarm_threshold = local.cfg.alarm_errors
  tags                  = local.tags
}

# ----------------------------------------------------------------------- kubernetes
data "kubernetes_nodes" "cluster" {}

locals {
  node_ip = one([
    for a in data.kubernetes_nodes.cluster.nodes[0].status[0].addresses : a.address if a.type == "InternalIP"
  ])
}

resource "random_password" "admin_token" {
  length  = 24
  special = false
}

module "k8s_env" {
  source      = "../modules/k8s-env"
  env         = local.env
  admin_token = random_password.admin_token.result
  config = {
    ENV                 = local.env
    AWS_REGION          = local.region
    AWS_ENDPOINT_URL    = local.floci_from_pods
    LOG_TO_CLOUDWATCH   = "true"
    METRICS_ENABLED     = "true"
    PEAK_HOURS          = local.cfg.peak_hours
    TABLE_RESERVATIONS  = module.dynamodb.table_names.reservations
    TABLE_BILLING       = module.dynamodb.table_names.billing
    TABLE_DISPATCH      = module.dynamodb.table_names.dispatch
    TABLE_SAGAS         = module.dynamodb.table_names.sagas
    TABLE_FEATURE_FLAGS = module.feature_flags.table_name
    # Las llamadas entre servicios pasan por Traefik para que el reparto Canary aplique también internamente.
    STATION_URL  = "${local.traefik_svc}/${local.env}/station-reservation"
    BILLING_URL  = "${local.traefik_svc}/${local.env}/billing-wallet"
    DISPATCH_URL = "${local.traefik_svc}/${local.env}/energy-dispatch"
  }
}

# ---------------------------------------------------------------------- api gateway
module "api_gateway" {
  source                 = "../modules/api-gateway"
  env                    = local.env
  vpc_id                 = module.network.vpc_id
  private_subnet_ids     = module.network.private_subnet_ids
  vpce_security_group_id = module.vpc_endpoints.vpce_security_group_id
  node_ip                = local.node_ip
  tags                   = local.tags
}
