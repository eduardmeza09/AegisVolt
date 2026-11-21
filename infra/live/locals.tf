# Parametrización por ambiente: TODO deriva de terraform.workspace.
locals {
  env    = terraform.workspace
  region = "us-east-1"
  azs    = ["us-east-1a", "us-east-1b"]

  settings = {
    dev = {
      cidr          = "10.10.0.0/16"
      log_retention = 7
      pitr          = false
      peak_hours    = "0-24" # siempre "hora pico" en dev para poder demostrar el surge pricing
      alarm_errors  = 20
      flags         = { ENABLE_DYNAMIC_SURGE_PRICING = true, ENABLE_FAST_CHARGE_BOOST = true, SIMULATE_CHARGER_HARDWARE_FAULT = false }
    }
    test = {
      cidr          = "10.20.0.0/16"
      log_retention = 14
      pitr          = false
      peak_hours    = "17-21"
      alarm_errors  = 10
      flags         = { ENABLE_DYNAMIC_SURGE_PRICING = true, ENABLE_FAST_CHARGE_BOOST = true, SIMULATE_CHARGER_HARDWARE_FAULT = false }
    }
    prod = {
      cidr          = "10.30.0.0/16"
      log_retention = 30
      pitr          = true
      peak_hours    = "17-21"
      alarm_errors  = 5
      flags         = { ENABLE_DYNAMIC_SURGE_PRICING = false, ENABLE_FAST_CHARGE_BOOST = false, SIMULATE_CHARGER_HARDWARE_FAULT = false }
    }
  }

  # lookup con default {} => si el workspace no es válido, el guardián (main.tf) falla con un mensaje claro.
  cfg = lookup(local.settings, local.env, local.settings["dev"])

  services = ["station-reservation", "billing-wallet", "energy-dispatch", "graphql-gateway"]
  tags     = { Project = "aegisvolt", Environment = local.env, ManagedBy = "terraform", Workspace = terraform.workspace }

  # Endpoint de Floci visto DESDE los pods (IP fija en la red aegisvolt-net de docker-compose).
  floci_from_pods = "http://172.30.0.10:4566"
  traefik_svc     = "http://traefik.traefik.svc.cluster.local"
}
