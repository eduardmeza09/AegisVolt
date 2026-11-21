# CloudWatch por ambiente: log groups /aegisvolt/<env>/<servicio> y alarmas de errores
# sobre las métricas custom AegisVolt/<env> que publican los microservicios.

variable "env" { type = string }
variable "services" { type = list(string) }
variable "retention_days" { type = number }
variable "error_alarm_threshold" { type = number }
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_cloudwatch_log_group" "svc" {
  for_each          = toset(var.services)
  name              = "/aegisvolt/${var.env}/${each.key}"
  retention_in_days = var.retention_days
  tags              = merge(var.tags, { Service = each.key })
}

resource "aws_cloudwatch_log_group" "prefect" {
  name              = "/aegisvolt/${var.env}/prefect-observability"
  retention_in_days = var.retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  for_each            = toset(var.services)
  alarm_name          = "aegisvolt-${var.env}-${each.key}-errors"
  alarm_description   = "ErrorCount de ${each.key} en ${var.env} por encima del umbral"
  namespace           = "AegisVolt/${var.env}"
  metric_name         = "ErrorCount"
  dimensions          = { Service = each.key }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 2
  threshold           = var.error_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "orphan_sagas" {
  alarm_name          = "aegisvolt-${var.env}-orphan-sagas"
  alarm_description   = "Prefect detecto sagas huerfanas o con compensacion fallida en ${var.env}"
  namespace           = "AegisVolt/${var.env}"
  metric_name         = "OrphanSagas"
  dimensions          = { Service = "prefect-observability" }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

output "log_groups" { value = [for g in aws_cloudwatch_log_group.svc : g.name] }
