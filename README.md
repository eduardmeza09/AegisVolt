# AegisVolt

Plataforma cloud-native de gestión de carga para flotas eléctricas y electrolineras B2B. Usa SAGA por orquestación, Feature Flags por ambiente, Terraform Workspaces, Canary con Argo Rollouts y observabilidad con CloudWatch y Prefect, todo sobre **Floci** (emulador de AWS).

- Especificación: [Proyecto Final (AegisVolt).md](Proyecto%20Final%20-%20Patrones%20Arquitect%C3%B3nicos%20Avanzados%20(AegisVolt).md)
- Plan: [PLAN.md](PLAN.md)
- Arquitectura y decisiones: [docs/arquitectura.md](docs/arquitectura.md)
- Runbook de la defensa: [docs/runbook-defensa.md](docs/runbook-defensa.md)
- Frontend: [docs/frontend.md](docs/frontend.md)

## Estructura

| Ruta | Contenido |
|---|---|
| `services/` | 4 microservicios Python (FastAPI) + librería común `aegis_common` + tests |
| `services/graphql_gateway/schema.graphql` | Contrato GraphQL (validado en CI) |
| `frontend/` | React + Vite + TS (nginx), servido en `/web` del API Gateway de cada ambiente |
| `infra/bootstrap` | Bucket S3 versionado del tfstate + tabla de locks |
| `infra/platform`, `infra/platform-addons` | VPC de plataforma + EKS + ECR; Traefik + Argo Rollouts |
| `infra/live` | Stack por **workspace** (`dev`/`test`/`prod`): VPC, VPCE, peering, DynamoDB, flags, CloudWatch, API Gateway, namespace |
| `k8s/` | Kustomize: Rollouts canary, TraefikService ponderado, AnalysisTemplate; overlays por ambiente |
| `observability/prefect` | Flows de salud, auditoría SAGA y trazas |
| `scripts/` | `up`, `deploy`, `flags`, `trace`, `restore-tfstate`, `seed`, `kubeconfig`, `apply-rulesets` |
| `.github/workflows` | `ci.yml` (PR) y `cd.yml` (merge) |

## Ramas y promoción

`feature/*` → PR → `dev` → PR → `test` → PR → `prod`. El ruleset `protected-env-branches` bloquea el push directo, el force push y el borrado, y exige estos checks: `promotion-guard`, `lint-build`, `unit-tests`, `integration-tests`, `e2e-tests` y `terraform-plan`.

## Arranque rápido (entorno nuevo)

```bash
docker compose up -d floci
(cd infra/bootstrap && mv backend.tf backend.tf.off && terraform init && terraform apply && mv backend.tf.off backend.tf && terraform init -migrate-state -force-copy)
(cd infra/platform && terraform init && terraform apply)
./scripts/kubeconfig.sh
(cd infra/platform-addons && terraform init && terraform apply)
cd infra/live && terraform init && for e in dev test prod; do terraform workspace select -or-create $e && terraform apply -auto-approve; done; cd -
./scripts/deploy.sh dev                                          # build + Canary + seed
```

Después de reiniciar el PC: `./scripts/up.sh`.

## Desarrollo local sin Kubernetes

```bash
docker compose up -d floci
services/.venv/Scripts/python scripts/seed.py --env local --create-tables
docker compose --profile app up -d --build        # GraphQL en http://localhost:8080/graphql
```
