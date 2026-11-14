#!/usr/bin/env bash
# Aplica (crea o actualiza) el ruleset que protege dev/test/prod.
#   ./scripts/apply-rulesets.sh base   -> bloquea force push, borrado y push directo (exige PR)
#   ./scripts/apply-rulesets.sh full   -> base + checks de CI obligatorios (usar cuando ci.yml ya exista)
# Requiere: gh autenticado y python en PATH.
set -euo pipefail

MODE="${1:-base}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
NAME="protected-env-branches"
PAYLOAD="$(mktemp)"

python - "$ROOT" "$MODE" > "$PAYLOAD" <<'PY'
import json, sys, pathlib
root, mode = pathlib.Path(sys.argv[1]), sys.argv[2]
rs = json.loads((root / ".github/rulesets/env-branches.base.json").read_text(encoding="utf-8"))
if mode == "full":
    rs["rules"].append(json.loads((root / ".github/rulesets/required-checks.json").read_text(encoding="utf-8")))
elif mode != "base":
    sys.exit(f"modo desconocido: {mode} (usa base|full)")
print(json.dumps(rs))
PY

ID="$(gh api "repos/$REPO/rulesets" -q ".[] | select(.name==\"$NAME\") | .id" || true)"
if [[ -n "$ID" ]]; then
  gh api -X PUT "repos/$REPO/rulesets/$ID" --input "$PAYLOAD" -q '"actualizado ruleset \(.id) (\(.rules | length) reglas)"'
else
  gh api -X POST "repos/$REPO/rulesets" --input "$PAYLOAD" -q '"creado ruleset \(.id) (\(.rules | length) reglas)"'
fi
rm -f "$PAYLOAD"
