#!/usr/bin/env bash
# Historial y restauración del terraform.tfstate de un workspace (bucket S3 versionado).
#   ./scripts/restore-tfstate.sh list    <env>               # versiones del estado
#   ./scripts/restore-tfstate.sh show    <env> <version-id>  # descarga y resume una versión
#   ./scripts/restore-tfstate.sh restore <env> <version-id>  # la convierte en la versión vigente
#
# restore = copy-object de la versión antigua sobre la misma clave => se crea una NUEVA versión
# con el contenido viejo (no se destruye historial; la versión corrupta sigue disponible).
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test} AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
A=(aws --endpoint-url "${AWS_ENDPOINT_URL:-http://localhost:4566}" --region us-east-1)
BUCKET="aegisvolt-tfstate"
CMD="${1:?uso: list|show|restore <env> [version-id]}"; ENV="${2:?falta ambiente (dev|test|prod|platform)}"
if [[ "$ENV" == "platform" || "$ENV" == "bootstrap" || "$ENV" == "platform-addons" ]]; then
  KEY="$ENV/terraform.tfstate"
else
  KEY="env:/$ENV/aegisvolt/terraform.tfstate"
fi
ROOT="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"

case "$CMD" in
  list)
    echo "s3://$BUCKET/$KEY"
    "${A[@]}" s3api list-object-versions --bucket "$BUCKET" --prefix "$KEY" \
      --query "Versions[?Key=='$KEY'].[VersionId, LastModified, Size, IsLatest]" --output table ;;
  show)
    VID="${3:?falta version-id}"; OUT="$ROOT/.tfstate-$ENV-$VID.json"
    "${A[@]}" s3api get-object --bucket "$BUCKET" --key "$KEY" --version-id "$VID" "$OUT" >/dev/null
    python -c "import json,sys;s=json.load(open(sys.argv[1]));print('serial',s['serial'],'lineage',s['lineage'],'recursos',len(s['resources']))" "$OUT"
    echo "descargado en $OUT" ;;
  restore)
    VID="${3:?falta version-id}"
    "${A[@]}" s3api copy-object --bucket "$BUCKET" --key "$KEY" \
      --copy-source "$BUCKET/$KEY?versionId=$VID" --query 'VersionId' --output text \
      | xargs -I{} echo "restaurada: nueva versión vigente {} (copia de $VID)"
    echo "Siguiente paso: cd infra/live && terraform workspace select $ENV && terraform plan  (verificar drift)" ;;
  *) echo "comando desconocido"; exit 2 ;;
esac
