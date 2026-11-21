# Estado remoto en S3 versionado. Con workspaces, Terraform guarda cada ambiente en
#   s3://aegisvolt-tfstate/env:/<workspace>/aegisvolt/terraform.tfstate
# => dev, test y prod tienen archivos de estado (y versiones/backups) totalmente separados.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws        = { source = "hashicorp/aws", version = "~> 6.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.36" }
    random     = { source = "hashicorp/random", version = "~> 3.6" }
  }
  backend "s3" {
    bucket                      = "aegisvolt-tfstate"
    key                         = "aegisvolt/terraform.tfstate"
    workspace_key_prefix        = "env:"
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
