# Aislamiento del ambiente dentro del clúster compartido:
# namespace aegisvolt-<env> + ResourceQuota + LimitRange + NetworkPolicy + ConfigMap + Secret.

variable "env" { type = string }
variable "config" {
  description = "Variables de entorno comunes a los microservicios de este ambiente"
  type        = map(string)
}
variable "admin_token" {
  type      = string
  sensitive = true
}
variable "quota_memory" {
  type    = string
  default = "1536Mi"
}

resource "kubernetes_namespace_v1" "env" {
  metadata {
    name   = "aegisvolt-${var.env}"
    labels = { "aegisvolt.io/env" = var.env, "app.kubernetes.io/part-of" = "aegisvolt" }
  }
}

resource "kubernetes_resource_quota_v1" "env" {
  metadata {
    name      = "aegisvolt-quota"
    namespace = kubernetes_namespace_v1.env.metadata[0].name
  }
  spec {
    hard = {
      "limits.memory" = var.quota_memory
      "pods"          = "20"
    }
  }
}

resource "kubernetes_limit_range_v1" "env" {
  metadata {
    name      = "aegisvolt-limits"
    namespace = kubernetes_namespace_v1.env.metadata[0].name
  }
  spec {
    limit {
      type            = "Container"
      default         = { memory = "160Mi", cpu = "500m" }
      default_request = { memory = "96Mi", cpu = "50m" }
    }
  }
}

# Solo se admite tráfico desde el propio namespace y desde Traefik (ingress / reparto canary).
# Un pod de aegisvolt-test NO puede hablar con aegisvolt-prod.
resource "kubernetes_network_policy_v1" "isolate" {
  metadata {
    name      = "isolate-environment"
    namespace = kubernetes_namespace_v1.env.metadata[0].name
  }
  spec {
    pod_selector {}
    policy_types = ["Ingress"]
    ingress {
      from {
        pod_selector {}
      }
      from {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "traefik" }
        }
      }
    }
  }
}

resource "kubernetes_config_map_v1" "env" {
  metadata {
    name      = "aegisvolt-config"
    namespace = kubernetes_namespace_v1.env.metadata[0].name
  }
  data = var.config
}

resource "kubernetes_secret_v1" "admin" {
  metadata {
    name      = "aegisvolt-admin"
    namespace = kubernetes_namespace_v1.env.metadata[0].name
  }
  data = { ADMIN_TOKEN = var.admin_token }
}

output "namespace" { value = kubernetes_namespace_v1.env.metadata[0].name }
