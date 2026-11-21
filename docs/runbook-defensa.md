# Runbook de la defensa

Todos los comandos se ejecutan desde la raíz del repo en **Git Bash**.

## 0. Arranque (1 h antes)

```bash
docker compose up -d floci && ./scripts/up.sh          # Floci + EKS + apply de los 3 workspaces + Prefect
powershell -ExecutionPolicy Bypass -File scripts/start-runner.ps1   # runner de GitHub Actions
powershell -ExecutionPolicy Bypass -File scripts/start-prefect.ps1           # flows programados (health 5 min, auditoría 10 min)
export KUBECONFIG=$HOME/.kube/aegisvolt.yaml
for e in dev test prod; do (cd infra/live && terraform workspace select $e >/dev/null && echo "$e: $(terraform output -raw graphql_url)"); done
```

Si falta RAM, cierra el navegador pesado. Docker está limitado a 6 GB (`.wslconfig`).

---

## 1. IaC, S3 y redes (30 %)

**¿Por qué `apply` en test no sobrescribe prod?**
```bash
cd infra/live
terraform workspace list                       # * dev / test / prod
terraform workspace select test && terraform state list | head      # solo recursos de test
aws --endpoint-url http://localhost:4566 s3 ls s3://aegisvolt-tfstate --recursive   # env:/dev, env:/test, env:/prod
```
Respuesta: el workspace decide la clave del estado (`env:/<ws>/...`) y el sufijo de todos los nombres (`locals.tf`). El guardián `workspace_guard` impide usar `default`. Detalle en `docs/arquitectura.md` §2.

**Versiones del tfstate de dev y cómo restaurar**
```bash
./scripts/restore-tfstate.sh list dev
./scripts/restore-tfstate.sh show dev <versionId-anterior>
./scripts/restore-tfstate.sh restore dev <versionId-anterior>   # crea una versión nueva con el contenido viejo
cd infra/live && terraform workspace select dev && terraform plan
```

**Recorrido del paquete API GW → pod (VPCE, rutas, SG)**: `docs/arquitectura.md` §4. Evidencia:
```bash
A="aws --endpoint-url http://localhost:4566"
$A ec2 describe-vpc-endpoints --query 'VpcEndpoints[].[VpcEndpointType,ServiceName,VpcId]' --output table
$A ec2 describe-route-tables --query 'RouteTables[].{rt:RouteTableId,vpc:VpcId,routes:Routes[].DestinationCidrBlock}'
$A apigatewayv2 get-vpc-links --query 'Items[].[Name,VpcLinkId]' --output table
$A elbv2 describe-load-balancers --query 'LoadBalancers[].[LoadBalancerName,Scheme,Type]' --output table
$A dynamodb list-tables     # 15 tablas de ambiente (5 x 3) + tflock
```

## 2. CI/CD y Canary (25 %)

**Push directo o force push a test**
```bash
git switch test && git commit --allow-empty -m "push directo" && git push origin test   # GH013 ... must be made through a pull request
git push --force origin test                                                            # GH013 ... Cannot force-push
git reset --hard origin/test
```
La regla es el ruleset `protected-env-branches` (Settings → Rules), definido en `.github/rulesets/` y aplicado con `scripts/apply-rulesets.sh full`. No tiene bypass actors.

**PR inválido (feature → test)**: falla el check `promotion-guard`.

**¿Cómo decide el YAML el ambiente del apply?** En `.github/workflows/cd.yml`:
- `on.push.branches: [dev, test, prod]`. Como solo se puede llegar por merge de PR, un push siempre equivale a un merge.
- `TARGET_ENV: ${{ github.ref_name }}`, seguido de `terraform workspace select -or-create "$TARGET_ENV"` y `terraform apply -auto-approve`.
- `concurrency: deploy-<rama>` y `environment: <rama>`.
- En el PR, `ci.yml` hace lo mismo con `github.base_ref` (la rama destino) para `terraform plan`.

**¿Qué métrica evalúa el Canary?** `ErrorCount / RequestCount` del pod canary en CloudWatch (`AegisVolt/<env>`, dimensión `PodTemplateHash`) < 2 % con ≥ 10 muestras. Se evalúa al 20 % y al 50 %. Detalle en `docs/arquitectura.md` §7.
```bash
FAULT_INJECTION_RATE=0.3 FAULT_SERVICE=billing-wallet ./scripts/deploy.sh dev demo-mala   # análisis falla => abort
kubectl argo rollouts get rollout billing-wallet -n aegisvolt-dev
kubectl -n aegisvolt-dev logs job/$(kubectl -n aegisvolt-dev get jobs --sort-by=.metadata.creationTimestamp -o name | grep billing | tail -1 | cut -d/ -f2)
./scripts/deploy.sh dev $(git rev-parse --short HEAD)        # versión sana => 20% -> 50% -> 100%
```

## 3. SAGA y Feature Flags (25 %)

**Fallo en test y compensación visible en DynamoDB**
```bash
./scripts/flags.sh set test SIMULATE_CHARGER_HARDWARE_FAULT true      # sin redesplegar (TTL 5 s)
URL=$(cd infra/live && terraform workspace select test >/dev/null && terraform output -raw graphql_url)
curl -s -X POST "$URL" -H 'content-type: application/json' -d '{"query":"mutation { reserveAndStartCharging(input:{fleetId:\"fleet-rapido\", stationId:\"st-bog-01\", connectorId:\"c1\", estimatedKwh:30}) { sagaId status errorCode steps { name status detail } } }"}'
A="aws --endpoint-url http://localhost:4566"
$A dynamodb get-item --table-name aegisvolt-sagas-test --key '{"saga_id":{"S":"<sagaId>"}}'
$A dynamodb query --table-name aegisvolt-billing-test --key-condition-expression "fleet_id = :f" --expression-attribute-values '{":f":{"S":"fleet-rapido"}}' --query 'Items[].[sk.S,amount.N,balance.N]' --output table   # HOLD + REFUND
$A dynamodb get-item --table-name aegisvolt-reservations-test --key '{"station_id":{"S":"st-bog-01"},"connector_id":{"S":"c1"}}' --query 'Item.[status.S,last_saga_id.S]'   # AVAILABLE
./scripts/flags.sh list prod                                              # prod intacto
./scripts/flags.sh set test SIMULATE_CHARGER_HARDWARE_FAULT false
```

**Idempotencia**: ejecuta `mutation { retryCompensation(sagaId:"<sagaId>") { status steps { name detail idempotentReplay } } }`. Los pasos `*_REPLAY` salen con `idempotentReplay: true`, el saldo no cambia y no aparece un segundo REFUND. Tests: `services/tests/unit/test_idempotency.py`. Explicación en `docs/arquitectura.md` §5.

## 4. Observabilidad y frontend (20 %)

```bash
./scripts/trace.sh test last-compensated             # correlation_id en los 4 log groups /aegisvolt/test/*
```
- En la UI de Prefect (http://localhost:4200), abre Deployments, luego `aegisvolt-saga-consistency-audit` y ejecuta **Quick run**. En Artifacts aparecen `aegisvolt-saga-audit` y `aegisvolt-env-health`.
- `aegisvolt-trace-saga` (bajo demanda) recibe `env` y `correlation_id` y genera la traza como artifact.
- Flags en dev sin redesplegar: `./scripts/flags.sh set dev ENABLE_DYNAMIC_SURGE_PRICING false`. El frontend de dev cambia a los ≤ 5 s y el de prod no.

## 5. Tests

```bash
cd services && uv run pytest tests/unit -q                                  # 19 tests (moto)
AWS_ENDPOINT_URL=http://localhost:4566 uv run pytest tests/integration -q   # contra Floci
```
