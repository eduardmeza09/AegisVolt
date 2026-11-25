# Plataforma compartida (un solo estado, sin workspaces): VPC de plataforma + clúster EKS + ECR.
# Por restricción de RAM local (16 GB) hay UN clúster EKS con un namespace por ambiente;
# los datos, la red de cada ambiente, los logs y el estado siguen aislados por workspace en infra/live.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" {
    bucket                      = "aegisvolt-tfstate"
    key                         = "platform/terraform.tfstate"
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

variable "aws_endpoint" {
  type    = string
  default = "http://localhost:4566"
}

variable "cluster_name" {
  type    = string
  default = "aegisvolt-eks"
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true
  endpoints {
    ec2 = var.aws_endpoint
    eks = var.aws_endpoint
    ecr = var.aws_endpoint
    iam = var.aws_endpoint
    sts = var.aws_endpoint
  }
  default_tags {
    tags = { Project = "aegisvolt", Stack = "platform", ManagedBy = "terraform" }
  }
}

locals {
  azs      = ["us-east-1a", "us-east-1b"]
  cidr     = "10.0.0.0/16"
  services = ["station-reservation", "billing-wallet", "energy-dispatch", "graphql-gateway"]
}

module "network" {
  source = "../modules/network"
  name   = "aegisvolt-platform"
  cidr   = local.cidr
  azs    = local.azs
}

# VPC Endpoints de la VPC de plataforma: los pods (nodos EKS en subredes privadas, sin ruta a
# internet) salen a DynamoDB/S3 por los Gateway VPCE y a CloudWatch/STS por los Interface VPCE.
# Los VPCE Gateway no se comparten por peering: cada VPC necesita los suyos.
module "vpc_endpoints" {
  source                  = "../modules/vpc-endpoints"
  name                    = "aegisvolt-platform"
  vpc_id                  = module.network.vpc_id
  vpc_cidr                = local.cidr
  region                  = "us-east-1"
  private_subnet_ids      = module.network.private_subnet_ids
  private_route_table_ids = [module.network.private_route_table_id]
}

resource "aws_iam_role" "eks_cluster" {
  name = "aegisvolt-eks-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_security_group" "eks_cluster" {
  name        = "aegisvolt-eks-cluster"
  description = "Plano de control y nodos EKS: solo trafico interno de las VPC de AegisVolt"
  vpc_id      = module.network.vpc_id

  ingress {
    description = "HTTPS API server desde VPCs internas"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
  ingress {
    description = "NodePort Traefik (destino del NLB / VPC Link de cada ambiente)"
    from_port   = 30080
    to_port     = 30080
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_eks_cluster" "this" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "1.31"

  vpc_config {
    subnet_ids              = module.network.private_subnet_ids
    security_group_ids      = [aws_security_group.eks_cluster.id]
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster]
}

# Registro de imágenes: un repositorio por microservicio; la etiqueta identifica commit/ambiente.
resource "aws_ecr_repository" "svc" {
  for_each             = toset(local.services)
  name                 = "aegisvolt/${each.key}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "svc" {
  for_each   = aws_ecr_repository.svc
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Conservar las ultimas 20 imagenes"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

output "cluster_name" { value = aws_eks_cluster.this.name }
output "cluster_endpoint" { value = aws_eks_cluster.this.endpoint }
output "cluster_ca" { value = aws_eks_cluster.this.certificate_authority[0].data }
output "platform_vpc_id" { value = module.network.vpc_id }
output "platform_vpc_cidr" { value = local.cidr }
output "platform_private_route_table_id" { value = module.network.private_route_table_id }
output "platform_private_subnet_ids" { value = module.network.private_subnet_ids }
output "eks_security_group_id" { value = aws_security_group.eks_cluster.id }
output "platform_vpc_endpoints" {
  value = merge(module.vpc_endpoints.gateway_endpoint_ids, module.vpc_endpoints.interface_endpoint_ids)
}
output "ecr_repositories" { value = { for k, r in aws_ecr_repository.svc : k => r.repository_url } }
