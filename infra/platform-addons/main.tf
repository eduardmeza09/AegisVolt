# Addons de clúster (compartidos): Traefik (ingress + reparto ponderado de tráfico para el Canary)
# y Argo Rollouts (controlador de despliegues progresivos). Requiere ~/.kube/aegisvolt.yaml
# generado por scripts/kubeconfig.sh tras aplicar infra/platform.

terraform {
  required_version = ">= 1.10"
  required_providers {
    helm       = { source = "hashicorp/helm", version = "~> 2.17" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.36" }
  }
  backend "s3" {
    bucket                      = "aegisvolt-tfstate"
    key                         = "platform-addons/terraform.tfstate"
    region                      = "us-east-1"
    use_lockfile                = true
    encrypt                     = true
    access_key                  = "test"
    secret_key                  = "test"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_path_style              = true
    endpoints = {
      s3  = "http://localhost:4566"
      sts = "http://localhost:4566"
    }
  }
}

variable "kubeconfig_path" {
  type    = string
  default = "~/.kube/aegisvolt.yaml"
}

provider "helm" {
  kubernetes {
    config_path = pathexpand(var.kubeconfig_path)
  }
}

provider "kubernetes" {
  config_path = pathexpand(var.kubeconfig_path)
}

resource "helm_release" "traefik" {
  name             = "traefik"
  namespace        = "traefik"
  create_namespace = true
  repository       = "https://traefik.github.io/charts"
  chart            = "traefik"
  version          = "42.4.0"
  wait             = true
  timeout          = 600

  values = [yamlencode({
    deployment = { replicas = 1 }
    service    = { spec = { type = "NodePort" } }
    ports = {
      web       = { nodePort = 30080 }
      websecure = { expose = { default = false } }
    }
    providers = {
      kubernetesCRD     = { allowCrossNamespace = true }
      kubernetesIngress = { enabled = false }
    }
    ingressRoute = { dashboard = { enabled = false } }
    resources = {
      requests = { cpu = "50m", memory = "64Mi" }
      limits   = { memory = "128Mi" }
    }
  })]
}

resource "helm_release" "argo_rollouts" {
  name             = "argo-rollouts"
  namespace        = "argo-rollouts"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-rollouts"
  version          = "2.43.11"
  wait             = true
  timeout          = 600

  values = [yamlencode({
    dashboard = { enabled = false }
    controller = {
      replicas = 1
      resources = {
        requests = { cpu = "50m", memory = "64Mi" }
        limits   = { memory = "192Mi" }
      }
    }
  })]
}

output "traefik_node_port" { value = 30080 }
