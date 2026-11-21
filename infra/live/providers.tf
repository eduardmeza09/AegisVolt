variable "aws_endpoint" {
  description = "Endpoint de Floci (o null para AWS real)"
  type        = string
  default     = "http://localhost:4566"
}

variable "kubeconfig_path" {
  type    = string
  default = "~/.kube/aegisvolt.yaml"
}

provider "aws" {
  region                      = local.region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true
  endpoints {
    apigatewayv2 = var.aws_endpoint
    cloudwatch   = var.aws_endpoint
    dynamodb     = var.aws_endpoint
    ec2          = var.aws_endpoint
    elbv2        = var.aws_endpoint
    logs         = var.aws_endpoint
    s3           = var.aws_endpoint
    sts          = var.aws_endpoint
  }
  default_tags {
    tags = local.tags
  }
}

provider "kubernetes" {
  config_path = pathexpand(var.kubeconfig_path)
}
