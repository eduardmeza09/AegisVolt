#!/usr/bin/env bash
# Genera ~/.kube/aegisvolt.yaml para el clúster EKS de Floci.
#
# Por qué no `aws eks update-kubeconfig`: el webhook de tokens de EKS en Floci 2.4.0 rechaza
# los tokens de `aws eks get-token` (TokenReview authenticated=false). Como alternativa se usa
# la credencial de admin del k3s que Floci levantó para el clúster (documentado en docs/arquitectura.md).
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test} AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
CLUSTER="${1:-aegisvolt-eks}"
ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"
OUT="${KUBECONFIG_OUT:-$HOME/.kube/aegisvolt.yaml}"
mkdir -p "$(dirname "$OUT")"

API=$(aws --endpoint-url "$ENDPOINT_URL" --region us-east-1 eks describe-cluster --name "$CLUSTER" \
      --query cluster.endpoint --output text)
PORT="${API##*:}"
docker exec "floci-aws-eks-$CLUSTER" cat /etc/rancher/k3s/k3s.yaml \
  | sed "s#https://127.0.0.1:6443#https://127.0.0.1:${PORT}#; s#: default\$#: $CLUSTER#" > "$OUT"
echo "kubeconfig escrito en $OUT (API $API)"
