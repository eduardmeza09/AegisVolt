#!/usr/bin/env bash
# Despliegue de las 4 imágenes en el namespace del ambiente con estrategia Canary (Argo Rollouts).
#
#   ./scripts/deploy.sh <dev|test|prod> [tag]
#   FAULT_INJECTION_RATE=0.3 ./scripts/deploy.sh dev demo-bad   # demo: el análisis falla => rollback
#
# 1. docker build de cada servicio (APP_VERSION=<tag>)
# 2. importa las imágenes en el containerd del nodo k3s del EKS de Floci (ver docs: ECR push no
#    funciona desde Docker Desktop porque el hostname *.localhost del registro no resuelve)
# 3. kubectl apply del overlay => si ya había versión estable, Argo inicia el Canary 20% -> 50% -> 100%
# 4. espera cada Rollout; si el análisis de CloudWatch falla, Argo aborta y revierte => exit 1
set -euo pipefail
export MSYS_NO_PATHCONV=1
ENV="${1:?uso: deploy.sh <dev|test|prod> [tag]}"
TAG="${2:-$(git rev-parse --short HEAD)}"
[[ "$ENV" =~ ^(dev|test|prod)$ ]] || { echo "ambiente inválido: $ENV"; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
CLUSTER="${CLUSTER:-aegisvolt-eks}"
NODE="floci-aws-eks-$CLUSTER"
NS="aegisvolt-$ENV"
WINHOME="$(cygpath -m "$HOME" 2>/dev/null || echo "$HOME")"
export KUBECONFIG="${KUBECONFIG:-$WINHOME/.kube/aegisvolt.yaml}"
declare -A PKG=( [station-reservation]=station_reservation_service [billing-wallet]=billing_wallet_service
                 [energy-dispatch]=energy_dispatch_service [graphql-gateway]=graphql_gateway )
ROLL="kubectl-argo-rollouts"; command -v "$ROLL" >/dev/null || ROLL="$WINHOME/bin/kubectl-argo-rollouts.exe"

echo "==> [$ENV] build de imágenes tag=$TAG"
images=()
for svc in "${!PKG[@]}"; do
  docker build -q --build-arg SERVICE="${PKG[$svc]}" --build-arg APP_VERSION="$TAG" \
    -t "aegisvolt/$svc:$TAG" "$ROOT/services" >/dev/null
  images+=("aegisvolt/$svc:$TAG")
done
docker tag "aegisvolt/graphql-gateway:$TAG" aegisvolt/tools:latest
images+=(aegisvolt/tools:latest)

echo "==> [$ENV] importando ${#images[@]} imágenes en el nodo k3s ($NODE)"
docker save "${images[@]}" | docker exec -i "$NODE" ctr -n k8s.io images import - >/dev/null

echo "==> [$ENV] aplicando overlay k8s/overlays/$ENV"
RENDERED="$(kubectl kustomize "$ROOT/k8s/overlays/$ENV" | sed "s#:IMAGE_TAG#:$TAG#g")"
if [[ -n "${FAULT_INJECTION_RATE:-}" ]]; then
  # Solo afecta a FAULT_SERVICE (por defecto billing-wallet) para que la demo sea rápida y legible.
  FAULT_SERVICE="${FAULT_SERVICE:-billing-wallet}"
  RENDERED="$(echo "$RENDERED" | python "$ROOT/scripts/inject_fault.py" "$FAULT_SERVICE" "$FAULT_INJECTION_RATE")"
  echo "    (FAULT_INJECTION_RATE=${FAULT_INJECTION_RATE} en la versión nueva de ${FAULT_SERVICE})"
fi
echo "$RENDERED" | kubectl apply -f - >/dev/null

echo "==> [$ENV] esperando Rollouts (Canary 20% -> análisis CloudWatch -> 50% -> análisis -> 100%)"
failed=0
for svc in "${!PKG[@]}"; do
  if ! "$ROLL" status "$svc" -n "$NS" --timeout 600s; then
    echo "!! $svc: canary abortado => rollback automático a la versión estable"
    failed=1
  fi
done
"$ROLL" list rollouts -n "$NS" 2>/dev/null || kubectl get rollouts -n "$NS"

echo "==> [$ENV] seed idempotente de datos de demo"
PY="$ROOT/services/.venv/Scripts/python"; [[ -x "$PY" ]] || PY="$ROOT/services/.venv/bin/python"; [[ -x "$PY" ]] || PY=python
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test "$PY" "$ROOT/scripts/seed.py" --env "$ENV"
exit $failed
