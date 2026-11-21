# Database-per-Service: cada microservicio es dueño de su tabla; nombres sufijados por ambiente.

variable "env" { type = string }
variable "point_in_time_recovery" {
  type    = bool
  default = false
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_dynamodb_table" "reservations" {
  name         = "aegisvolt-reservations-${var.env}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "station_id"
  range_key    = "connector_id"
  attribute {
    name = "station_id"
    type = "S"
  }
  attribute {
    name = "connector_id"
    type = "S"
  }
  point_in_time_recovery { enabled = var.point_in_time_recovery }
  tags = merge(var.tags, { Owner = "station-reservation-service" })
}

resource "aws_dynamodb_table" "billing" {
  name         = "aegisvolt-billing-${var.env}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "fleet_id"
  range_key    = "sk"
  attribute {
    name = "fleet_id"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  point_in_time_recovery { enabled = var.point_in_time_recovery }
  tags = merge(var.tags, { Owner = "billing-wallet-service" })
}

resource "aws_dynamodb_table" "dispatch" {
  name         = "aegisvolt-dispatch-${var.env}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  range_key    = "sk"
  attribute {
    name = "session_id"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  point_in_time_recovery { enabled = var.point_in_time_recovery }
  tags = merge(var.tags, { Owner = "energy-dispatch-service" })
}

# Log de la SAGA (propiedad del orquestador en graphql-gateway). GSI para auditoría por estado (Prefect).
resource "aws_dynamodb_table" "sagas" {
  name         = "aegisvolt-sagas-${var.env}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "saga_id"
  attribute {
    name = "saga_id"
    type = "S"
  }
  attribute {
    name = "status"
    type = "S"
  }
  attribute {
    name = "updated_at"
    type = "S"
  }
  global_secondary_index {
    name            = "by_status"
    hash_key        = "status"
    range_key       = "updated_at"
    projection_type = "ALL"
  }
  point_in_time_recovery { enabled = var.point_in_time_recovery }
  tags = merge(var.tags, { Owner = "graphql-gateway-saga-orchestrator" })
}

output "table_names" {
  value = {
    reservations = aws_dynamodb_table.reservations.name
    billing      = aws_dynamodb_table.billing.name
    dispatch     = aws_dynamodb_table.dispatch.name
    sagas        = aws_dynamodb_table.sagas.name
  }
}
output "table_arns" {
  value = [aws_dynamodb_table.reservations.arn, aws_dynamodb_table.billing.arn, aws_dynamodb_table.dispatch.arn,
  aws_dynamodb_table.sagas.arn]
}
