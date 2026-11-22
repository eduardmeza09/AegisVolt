# AegisVolt: arquitectura implementada

## 1. Vista general

```
 Navegador (frontend)                                   GitHub (PR -> CI / merge -> CD)
        │ HTTPS                                                    │
        ▼                                                          ▼ self-hosted runner (PC)
 API Gateway HTTP API  aegisvolt-<env>-api, stage <env>     terraform workspace <rama> / deploy.sh
        │  (AWS real: VPC Link -> NLB interno -> peering)
        ▼
 Traefik NodePort 30080 (nodo EKS/k3s)  ── IngressRoute /<env>/<servicio> ──► TraefikService ponderado
        │                                                       (stable 80 % / canary 20 %)
        ▼  namespace aegisvolt-<env>  (ResourceQuota + LimitRange + NetworkPolicy)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ graphql-gateway (Strawberry) + orquestador SAGA ──► sagas-<env>, feature-flags-<env> │
 │    │ HTTP vía Traefik (x-correlation-id, x-saga-id, Idempotency-Key)               │
 │    ├──► station-reservation ──► aegisvolt-reservations-<env>                        │
 │    ├──► billing-wallet      ──► aegisvolt-billing-<env>  (ledger idempotente)       │
 │    └──► energy-dispatch     ──► aegisvolt-dispatch-<env> (sesiones + telemetría)    │
 └──────────────────────────────────────────────────────────────────────────────┘
        │ logs JSON (correlation_id) + métricas custom
        ▼
 CloudWatch Logs /aegisvolt/<env>/<servicio>   CloudWatch Metrics AegisVolt/<env>  ◄── Prefect flows
```

| Capa | Implementación |
|---|---|
| Emulación AWS | Floci 2.4.0 (`docker-compose.yml`), almacenamiento persistente, IP fija 172.30.0.10 |
| IaC | Terraform 4 stacks: `bootstrap` (bucket tfstate), `platform` (VPC + EKS + ECR), `platform-addons` (Traefik + Argo Rollouts), `live` (por workspace) |
| Cómputo | EKS de Floci = k3s real (v1.31), 1 clúster compartido, 1 namespace por ambiente |
| Servicios | Python 3.12, FastAPI, boto3, httpx, tenacity; imagen única parametrizada (`services/Dockerfile`) |
| API | GraphQL (Strawberry). Contrato en `services/graphql_gateway/schema.graphql` |
| Frontend | React + Vite + TS en nginx, un Deployment por namespace, publicado en `/<stage>/web/` del mismo API Gateway (mismo origen que GraphQL). Ver `docs/frontend.md` |
| Despliegue | Kustomize (`k8s/overlays/<env>`) + Argo Rollouts Canary + Traefik weighted |
| Observabilidad | CloudWatch Logs/Metrics/Alarms + Prefect 3 (`observability/prefect`) |

## 2. Aislamiento de ambientes (Terraform Workspaces)

- `infra/live` usa `terraform.workspace` como única fuente del ambiente (`locals.tf`). El recurso `terraform_data.workspace_guard` aborta si el workspace no es `dev`, `test` o `prod`.
- El backend S3 usa `workspace_key_prefix = "env:"`. Por eso cada ambiente tiene su propio objeto de estado:
  - `s3://aegisvolt-tfstate/env:/dev/aegisvolt/terraform.tfstate`
  - `s3://aegisvolt-tfstate/env:/test/aegisvolt/terraform.tfstate`
  - `s3://aegisvolt-tfstate/env:/prod/aegisvolt/terraform.tfstate`
- Todos los nombres llevan el sufijo del ambiente: `aegisvolt-billing-test`, `/aegisvolt/prod/billing-wallet`, `aegisvolt-dev-api`, la VPC `10.20.0.0/16` de test y el namespace `aegisvolt-prod`.
- **Por qué un `apply` en `test` no toca `prod`:** con el workspace `test`, Terraform carga y bloquea solo `env:/test/...`. Los recursos de prod no están en ese estado, así que Terraform no puede modificarlos ni destruirlos. Además, cada nombre es distinto, así que no hay colisiones.
- Los stacks compartidos (`platform`, `platform-addons`) tienen su propia clave (`platform/terraform.tfstate`) y el CD solo los aplica desde `dev`.

## 3. Backups del estado (S3 versionado)

`infra/bootstrap` crea el bucket con `aws_s3_bucket_versioning = Enabled`, cifrado SSE, bloqueo de acceso público y retención de 90 días para las versiones no vigentes. El estado del propio bootstrap también se migró al bucket. Cada `apply` crea una versión nueva.

- Listar el historial: `./scripts/restore-tfstate.sh list dev`
- Inspeccionar una versión: `./scripts/restore-tfstate.sh show dev <versionId>`
- Restaurar: `./scripts/restore-tfstate.sh restore dev <versionId>`. Hace un `copy-object` de la versión antigua sobre la misma clave, lo que crea una versión vigente nueva. La versión corrupta no se borra y queda auditable. Después se ejecuta `terraform plan` para revisar el drift.
- El locking usa el lockfile nativo de S3 (`use_lockfile = true`, Terraform ≥ 1.10). Por eso en el historial aparecen objetos `.tflock`. Además existe la tabla `aegisvolt-tflock` para el locking clásico con DynamoDB.

## 4. Red: recorrido de un paquete (pregunta 6.1.3)

Por ambiente: una VPC (`10.10/16` dev, `10.20/16` test, `10.30/16` prod) con 2 subredes públicas y 2 privadas en 2 AZ, IGW, tabla de ruta pública (`0.0.0.0/0 → IGW`) y tabla de ruta privada **sin salida a internet**. La plataforma (EKS) vive en `10.0.0.0/16` y se conecta a cada ambiente por **VPC peering**, con rutas en ambas tablas privadas.

Camino de una petición GraphQL (topología declarada, AWS real `integration_mode = "vpc_link"`):

1. El cliente llama a API Gateway (`aegisvolt-<env>-api`, stage `<env>`, ruta `ANY /{proxy+}`).
2. La integración `HTTP_PROXY` con `connection_type = VPC_LINK` atraviesa el **VPC Link** (ENIs en las subredes privadas del ambiente, SG `aegisvolt-<env>-vpce`).
3. Llega al **NLB interno** (`aegisvolt-<env>-nlb`, listener TCP 80) y pasa al target group `aegisvolt-<env>-traefik` (IP de los nodos, puerto 30080, health check HTTP `/<env>/graphql-gateway/healthz`).
4. La tabla de ruta privada del ambiente envía `10.0.0.0/16` por el **peering**. El SG `aegisvolt-eks-cluster` admite 30080 y 443 solo desde `10.0.0.0/8`.
5. Traefik (NodePort 30080) aplica la IngressRoute `/<env>/graphql-gateway` (StripPrefix) y el TraefikService ponderado (stable/canary) entrega la petición al pod del gateway.
6. El gateway llama a los servicios por Traefik (`/<env>/<servicio>`). La NetworkPolicy del namespace solo admite tráfico del mismo namespace y de `traefik`.
7. Hacia DynamoDB y S3, el tráfico sale por los **Gateway VPCE**, que son rutas con prefix list en la tabla privada. Hacia CloudWatch Logs y Metrics y STS sale por los **Interface VPCE** (`logs`, `monitoring`, `sts`, con private DNS), y el Interface VPCE `execute-api` sirve para consumir APIs privadas desde la VPC. **Ningún salto sale a internet.**

**En Floci:** el plano de control de todos estos recursos existe (se crean y se ven con `aws ec2 describe-vpc-endpoints`, `aws elbv2 describe-load-balancers`, `aws apigatewayv2 get-vpc-links`). Lo que Floci 2.4.0 no emula es el plano de datos del VPC Link. Por eso `integration_mode = "direct"` (por defecto) apunta la integración `HTTP_PROXY` a la IP privada del nodo k3s (`data.kubernetes_nodes` la descubre en cada apply) en la red Docker privada `aegisvolt-net`. Cambiar a AWS real es cambiar una variable.

## 5. SAGA por orquestación

Orquestador: `services/graphql_gateway/saga.py`. Estado persistido en `aegisvolt-sagas-<env>`; cada transición se escribe **antes** del paso siguiente.

| Caso | Pasos registrados | Estado final |
|---|---|---|
| Éxito | RESERVE_CONNECTOR → HOLD_FUNDS → START_CHARGING | COMPLETED (luego FINISHED con `stopCharging`) |
| Fondos insuficientes (paso 2) | RESERVE_CONNECTOR → HOLD_FUNDS ✗ → COMPENSATE_RELEASE | COMPENSATED |
| Fallo de hardware (paso 3) | … → START_CHARGING ✗ → COMPENSATE_REFUND → COMPENSATE_RELEASE | COMPENSATED |
| Conector ocupado / ULTRA sin flag (paso 1) | RESERVE_CONNECTOR ✗ | FAILED (nada que compensar) |
| Compensación agota reintentos | … → COMPENSATION | COMPENSATION_FAILED (Prefect la marca como huérfana) |

Las compensaciones se reintentan con backoff exponencial (tenacity, 4 intentos) solo ante errores transitorios. Los errores de negocio (402 o `HARDWARE_FAULT`) no se reintentan.

### Idempotencia (pregunta 6.3.2)

- **Mutación:** `clientRequestId` se registra con un `PutItem ... attribute_not_exists` (`REQ#<id>` en la tabla de sagas). Si se repite, devuelve la misma saga y no crea otra.
- **Cada llamada** lleva `Idempotency-Key = <saga_id>:<paso>` y `x-saga-id`.
- **Reserva:** `ConditionExpression: status = AVAILABLE OR saga_id = :saga`. Si la misma saga reintenta, la respuesta es la misma; si es otra saga, recibe `CONNECTOR_UNAVAILABLE`, lo que también impide una doble reserva concurrente.
- **Liberar (compensación):** `ConditionExpression: saga_id = :saga`. Si se procesa dos veces, la condición falla y el servicio responde 200 con `idempotent_replay: true`, sin cambios. Nunca libera una reserva de otra saga.
- **Cobro y reembolso:** `TransactWriteItems` = `Put TXN#<saga>#HOLD|REFUND` con `attribute_not_exists(sk)` + `Update` del saldo. Si el asiento ya existe, la transacción **entera** se cancela, así que el dinero se mueve una sola vez. El reembolso devuelve exactamente lo retenido (lo lee del HOLD).
- **Activación:** `session_id = saga_id` con `attribute_not_exists`.
- **Demostración:** la mutación `retryCompensation(sagaId)` vuelve a ejecutar las compensaciones de una saga ya compensada. Los pasos `*_REPLAY` quedan con `idempotentReplay: true` y el saldo no cambia.

## 6. Feature Flags por ambiente

Tabla `aegisvolt-feature-flags-<env>`, sembrada por Terraform con `lifecycle { ignore_changes = [item] }`, para que un `apply` no pise los cambios hechos en caliente. Los servicios releen cada 5 s, así que no hace falta redesplegar. Para cambiar un flag: `./scripts/flags.sh set <env> <FLAG> true|false` o la mutación `setFeatureFlag`, con el header `x-admin-token` (`terraform output -raw admin_token`).

| Flag | dev | test | prod | Efecto |
|---|---|---|---|---|
| ENABLE_DYNAMIC_SURGE_PRICING | true | true | false | ×1.5 dentro de `PEAK_HOURS` (dev: 0-24; test y prod: 17-21, hora de Bogotá) |
| ENABLE_FAST_CHARGE_BOOST | true | true | false | Permite reservar conectores `ULTRA` de 350 kW |
| SIMULATE_CHARGER_HARDWARE_FAULT | false | false | false | energy-dispatch falla en el paso 3, lo que dispara el rollback |

## 7. Canary (pregunta 6.2.3)

- Cada servicio es un `Rollout` (1 réplica estable). El TraefikService `<svc>` reparte el tráfico entre `<svc>-stable` y `<svc>-canary`, y Argo Rollouts ajusta los pesos.
- Pasos: `setWeight 20` → pausa de 15 s → **análisis** → `setWeight 50` → pausa de 10 s → **análisis** → 100 %.
- El análisis (`k8s/base/analysis-template.yaml`) es un Job que ejecuta `aegis_common.canary_check`:
  1. Envía 150 peticiones a `/<env>/<svc>/v1/info` por Traefik. Con el peso al 20 %, unas 30 llegan al canary.
  2. Espera el flush de métricas y lee de CloudWatch `AegisVolt/<env>` las métricas `RequestCount` y `ErrorCount` con las dimensiones `Service=<svc>` y `PodTemplateHash=<hash del canary>`.
  3. **Condición de promoción:** `ErrorCount / RequestCount < 2 %` **y** `RequestCount ≥ 10`. Si no se cumple, `exit 1`, `failureLimit 0` y **abort**: el peso vuelve a 0 % y el ReplicaSet canary se elimina (rollback automático).
- Además, las `readinessProbe` y `livenessProbe` (`/readyz`, `/healthz`) impiden que un pod no listo reciba tráfico.
- Demo: `FAULT_INJECTION_RATE=0.3 FAULT_SERVICE=billing-wallet ./scripts/deploy.sh dev demo-mala`.

## 8. Limitaciones de Floci 2.4.0 y alternativas aplicadas

| Limitación encontrada | Alternativa |
|---|---|
| El webhook de tokens de EKS rechaza `aws eks get-token` | `scripts/kubeconfig.sh` usa la credencial de admin del k3s que creó Floci |
| `docker push` al ECR de Floci: el hostname `*.dkr.ecr...localhost` no resuelve en Docker Desktop | Los repos ECR existen (Terraform) pero las imágenes se importan con `ctr images import` en el nodo k3s (`imagePullPolicy: Never`) |
| k3s de Floci viene con `--disable=traefik` | Traefik se instala por Helm desde Terraform (`platform-addons`) |
| Plano de datos de VPC Link no emulado | `integration_mode = "direct"` (sección 4) |
| Al reiniciar Floci, el nodo k3s cambia de IP | `scripts/up.sh` regenera el kubeconfig y aplica de nuevo cada workspace. `data.kubernetes_nodes` actualiza la integración |
| Git Bash convierte rutas `/aegisvolt/...` | Los scripts exportan `MSYS_NO_PATHCONV=1` |
