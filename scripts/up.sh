#!/usr/bin/env bash
# Arranque completo tras reiniciar el PC / Docker:
#   Floci (persistente) -> Floci re-crea el k3s del EKS desde su estado -> kubeconfig
#   -> terraform apply en cada workspace (re-descubre la IP del nodo para la integración del API Gateway)
#   -> Prefect (UI http://localhost:4200)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose up -d floci
echo "esperando el clúster EKS..."
for _ in $(seq 1 60); do
  docker ps --format '{{.Names}}' | grep -q floci-aws-eks-aegisvolt-eks && break; sleep 3
done
sleep 10
./scripts/kubeconfig.sh
for env in ${ENVS:-dev test prod}; do
  (cd infra/live && terraform workspace select "$env" >/dev/null && \
   terraform apply -auto-approve -input=false -no-color | tail -1) || echo "aviso: apply de $env falló"
done
docker compose --profile prefect up -d prefect-server
echo "listo. GraphQL por ambiente: (cd infra/live && terraform workspace select dev && terraform output graphql_url)"
