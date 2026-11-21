# Tras el primer apply (estado local), el propio estado del bootstrap se migra al bucket:
#   terraform init -migrate-state -force-copy
terraform {
  backend "s3" {
    bucket                      = "aegisvolt-tfstate"
    key                         = "bootstrap/terraform.tfstate"
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
      s3       = "http://localhost:4566"
      dynamodb = "http://localhost:4566"
      sts      = "http://localhost:4566"
    }
  }
}
