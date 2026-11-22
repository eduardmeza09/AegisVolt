#!/usr/bin/env bash
# terraform init resistente a fallas de red: instala los providers desde un mirror local en disco.
#
#   ./scripts/tf-init.sh <directorio-terraform> [args extra de init]
#
# 1. Intenta `terraform init` usando SOLO el mirror local (sin internet) para hashicorp/*.
# 2. Si falta algún provider o versión (primera vez o cambio en .terraform.lock.hcl), lo descarga
#    al mirror con `terraform providers mirror` y reintenta.
# El mirror vive fuera del repo ($TF_MIRROR_DIR, por defecto ~/.terraform-mirror) y persiste entre
# ejecuciones del runner self-hosted. Los checksums se siguen validando contra .terraform.lock.hcl.
set -euo pipefail
DIR="${1:?uso: tf-init.sh <dir> [args de init]}"; shift || true
to_native() { cygpath -m "$1" 2>/dev/null || echo "$1"; }
MIRROR="$(to_native "${TF_MIRROR_DIR:-$HOME/.terraform-mirror}")"
mkdir -p "$MIRROR"
CFG="$MIRROR/terraformrc"
cat > "$CFG" <<EOF
provider_installation {
  filesystem_mirror {
    path    = "$MIRROR"
    include = ["registry.terraform.io/hashicorp/*"]
  }
  direct {
    exclude = ["registry.terraform.io/hashicorp/*"]
  }
}
EOF
export TF_CLI_CONFIG_FILE="$CFG"

if terraform -chdir="$DIR" init -input=false -no-color "$@" >/tmp/tf-init.log 2>&1; then
  echo "terraform init ($DIR): providers desde el mirror local"
  exit 0
fi
echo "terraform init ($DIR): faltan providers en el mirror; descargándolos (requiere red)"
( unset TF_CLI_CONFIG_FILE; terraform -chdir="$DIR" providers mirror "$MIRROR" )
terraform -chdir="$DIR" init -input=false -no-color "$@"
