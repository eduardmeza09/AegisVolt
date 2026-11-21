#!/usr/bin/env bash
# Feature Flags por ambiente SIN redesplegar (los servicios releen la tabla cada 5 s).
#   ./scripts/flags.sh list <env>
#   ./scripts/flags.sh set  <env> <FLAG> <true|false>
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test} AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
A=(aws --endpoint-url "${AWS_ENDPOINT_URL:-http://localhost:4566}" --region us-east-1)
CMD="${1:?uso: flags.sh list|set <env> [FLAG true|false]}"; ENV="${2:?falta el ambiente}"
TABLE="aegisvolt-feature-flags-$ENV"
case "$CMD" in
  list)
    "${A[@]}" dynamodb scan --table-name "$TABLE" \
      --query 'Items[].[flag_name.S, enabled.BOOL, updated_by.S, updated_at.S]' --output table ;;
  set)
    FLAG="${3:?falta el nombre del flag}"; VAL="${4:?true|false}"
    [[ "$VAL" =~ ^(true|false)$ ]] || { echo "valor inválido: $VAL"; exit 2; }
    NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    "${A[@]}" dynamodb update-item --table-name "$TABLE" --key "{\"flag_name\":{\"S\":\"$FLAG\"}}" \
      --update-expression "SET enabled = :v, updated_by = :u, updated_at = :t" \
      --condition-expression "attribute_exists(flag_name)" \
      --expression-attribute-values "{\":v\":{\"BOOL\":$VAL},\":u\":{\"S\":\"flags.sh\"},\":t\":{\"S\":\"$NOW\"}}" >/dev/null
    echo "[$ENV] $FLAG = $VAL (efectivo en <= 5 s, sin redespliegue; los demás ambientes no cambian)" ;;
  *) echo "comando desconocido: $CMD"; exit 2 ;;
esac
