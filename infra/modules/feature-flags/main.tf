# Feature Flags propias en DynamoDB: una tabla POR AMBIENTE => estado independiente.
# Terraform siembra el valor inicial; ignore_changes evita que un apply posterior pise los
# cambios hechos en caliente (scripts/flags.sh o mutación setFeatureFlag) sin redesplegar.

variable "env" { type = string }
variable "flags" {
  description = "Valor inicial de cada flag en este ambiente"
  type        = map(bool)
}
variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  descriptions = {
    ENABLE_DYNAMIC_SURGE_PRICING    = "Activa tarifas dinamicas (x1.5) en horas pico"
    ENABLE_FAST_CHARGE_BOOST        = "Habilita la reserva prioritaria de conectores de ultra-carga (ULTRA 350 kW)"
    SIMULATE_CHARGER_HARDWARE_FAULT = "Inyeccion de fallos: el cargador reporta error fisico (dispara rollback SAGA)"
  }
}

resource "aws_dynamodb_table" "flags" {
  name         = "aegisvolt-feature-flags-${var.env}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "flag_name"
  attribute {
    name = "flag_name"
    type = "S"
  }
  tags = merge(var.tags, { Owner = "platform-feature-flags" })
}

resource "aws_dynamodb_table_item" "flag" {
  for_each   = var.flags
  table_name = aws_dynamodb_table.flags.name
  hash_key   = aws_dynamodb_table.flags.hash_key
  item = jsonencode({
    flag_name   = { S = each.key }
    enabled     = { BOOL = each.value }
    description = { S = lookup(local.descriptions, each.key, "") }
    updated_by  = { S = "terraform" }
  })
  lifecycle {
    ignore_changes = [item]
  }
}

output "table_name" { value = aws_dynamodb_table.flags.name }
