"""Filtro stdin->stdout: fija FAULT_INJECTION_RATE en el Rollout de un servicio (demo de rollback del Canary).

uso: kubectl kustomize k8s/overlays/dev | python scripts/inject_fault.py billing-wallet 0.3
"""

import re
import sys

svc, rate = sys.argv[1], sys.argv[2]
docs = sys.stdin.read().split("\n---\n")
hits = 0
for i, doc in enumerate(docs):
    if "kind: Rollout" in doc and f"image: aegisvolt/{svc}:" in doc:
        docs[i], n = re.subn(r'(name: FAULT_INJECTION_RATE\n\s+value: )"0"', rf'\g<1>"{rate}"', doc)
        hits += n
if hits != 1:
    sys.exit(f"inject_fault: se esperaba 1 reemplazo para {svc}, hubo {hits}")
sys.stdout.write("\n---\n".join(docs))
