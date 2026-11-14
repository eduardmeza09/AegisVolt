# Plan de desarrollo — AegisVolt

## Contexto

Proyecto final individual de *Patrones Arquitectónicos Avanzados*: una plataforma cloud-native para reservar bahías de carga EV, retener saldo y activar sesiones de carga. El flujo pasa por 3 microservicios y se resuelve con una **SAGA con compensaciones**. Los ambientes `dev`, `test` y `prod` quedan aislados mediante **Terraform Workspaces**, el estado vive en S3 versionado, y hay CI/CD en GitHub con promoción lineal y **Canary**. La observabilidad usa CloudWatch y Prefect. En la defensa se califica cada pregunta como correcta o incorrecta y se piden demos en vivo, así que cada requisito debe poder **demostrarse con un comando**.

El directorio está vacío (solo contiene la especificación), así que el proyecto es greenfield.

**Decisiones tomadas**
- Restricciones fijas: **Floci** como emulador de AWS y **GitHub** para repositorio y CI.
- Lenguaje: Python 3.12 para servicios, GraphQL, Prefect, tests y scripts.
- SAGA por **orquestación**.
- Kubernetes con **EKS de Floci** (Floci levanta un k3s real por clúster).
- CI **híbrido**: lint y tests en runners de GitHub; plan, apply y deploy en un self-hosted runner con Floci persistente.

---

## 1. Stack tecnológico

| Capa | Elección |
|---|---|
| Emulación AWS | `floci/floci:<x.y.z>` fijado (nunca `latest`), puerto 4566, volumen persistente, socket Docker montado (necesario para EKS→k3s) |
| IaC | Terraform ≥ 1.10, `hashicorp/aws ~> 6.0` con `endpoints {}` hacia Floci para cada servicio usado, más los providers `kubernetes` y `helm` |
| Microservicios | FastAPI + Pydantic v2 + boto3 + httpx + tenacity (reintentos), gestionados con `uv` |
| GraphQL | Strawberry GraphQL sobre FastAPI (queries, mutations y una subscription opcional por graphql-ws) |
| Contenedores / K8s | Docker multi-stage (`python:3.12-slim`), Kustomize con overlays por ambiente, **Argo Rollouts** para el Canary, **Traefik** (ya viene en k3s) como traffic router |
| Registro de imágenes | ECR de Floci (`aws_ecr_repository`). Si k3s no puede hacer pull, se usa `ctr images import` |
| Feature Flags | Solución propia en DynamoDB: tabla `aegisvolt-feature-flags-${workspace}` y caché TTL de 5 s en los servicios |
| Logs y métricas | JSON estructurado (`python-json-logger`) enviado a CloudWatch Logs con `watchtower` (cliente boto3 apuntando a Floci), más `PutMetricData` |
| Orquestación de observabilidad | Prefect 3 (server y worker en docker-compose, UI en :4200) |
| Tests | pytest, pytest-asyncio, httpx TestClient; tflint, ruff, `terraform validate` |
| CI/CD | GitHub Actions y GitHub Rulesets (gratis porque el **repo es público**) |

### 1.1 Presupuesto de RAM (PC de 16 GB, ~4 GB libres en uso normal)
| Componente | RAM aprox. |
|---|---|
| Floci | ~400 MB |
| 1 clúster k3s (EKS de Floci) + Traefik + Argo Rollouts | ~700 MB |
| 12 pods estables (4 servicios × 3 ambientes × 1 réplica, ~70 MB c/u) + pods canary temporales | ~1–1,2 GB |
| Prefect server + worker | ~500 MB |
| Runner self-hosted (inactivo) | ~100 MB |
| **Total** | **~3 GB** |

- Configurar `%UserProfile%\.wslconfig` con `memory=5GB` y `swap=4GB`, para que Docker Desktop no deje sin memoria a Windows.
- En los pods: `resources.limits.memory: 128Mi` y uvicorn con 1 worker.
- El día de la defensa: cerrar el navegador pesado y el IDE extra.
- Si falta memoria: usar Prefect Cloud (plan gratuito) en lugar del server local, con el worker local. Ahorra ~400 MB.

---

## 2. Estructura del repositorio (monorepo)

```
aegisvolt/
├── services/
│   ├── libs/aegis_common/            # logging JSON, correlation_id, cliente de flags, helpers DynamoDB, métricas
│   ├── graphql-gateway/              # schema Strawberry + orquestador SAGA
│   │   └── schema.graphql            # SDL exportado (contrato con el frontend, validado en CI)
│   ├── station-reservation-service/
│   ├── billing-wallet-service/
│   └── energy-dispatch-service/      # incluye simulador de telemetría
├── infra/
│   ├── bootstrap/                    # bucket tfstate (versioning) + tabla de locks (estado local, una sola vez)
│   ├── modules/{network,vpc-endpoints,dynamodb,eks,api-gateway,ecr,observability,feature-flags,k8s-platform}
│   ├── live/                         # root module; usa terraform.workspace + locals por ambiente
│   └── github/                       # rulesets de ramas como IaC
├── k8s/
│   ├── base/                         # Rollout, Service, ConfigMap y AnalysisTemplate por servicio
│   └── overlays/{dev,test,prod}/
├── observability/prefect/            # flows + prefect.yaml (deployments programados)
├── tests/{e2e,integration}/
├── scripts/                          # flags.sh, restore-tfstate.sh, seed.py, trace.sh, load.py
├── frontend/                         # ← responsabilidad del compañero (sección 10)
├── docker-compose.yml                # floci, prefect-server, prefect-worker, floci-ui
├── .github/workflows/{ci.yml,cd.yml}
└── docs/{arquitectura.md, adr/, runbook-defensa.md}
```

---

## 3. Infraestructura como Código (30 %)

### 3.1 Backend remoto y backups
- `infra/bootstrap`: crea `aegisvolt-tfstate` con `aws_s3_bucket_versioning { status = "Enabled" }`, cifrado SSE y bloqueo de acceso público, más la tabla de lock `aegisvolt-tflock` (`LockID` de tipo S).
- `infra/live/backend.tf`: backend `s3` con `use_path_style = true`, endpoints de Floci y `workspace_key_prefix = "env:"`. Las claves resultantes son `env:/dev/aegisvolt/terraform.tfstate`, `env:/test/...` y `env:/prod/...`.
- `scripts/restore-tfstate.sh <env> [version-id]`:
  1. Lista las versiones con `aws s3api list-object-versions --prefix env:/<env>/`.
  2. Descarga la versión elegida con `get-object --version-id`.
  3. Hace `terraform state push` (o `copy-object` sobre sí mismo para convertirla en la versión actual).
  4. Valida con `terraform plan`.

### 3.2 Aislamiento por workspace
- `locals { env = terraform.workspace }`. Hay una validación que falla si el workspace no es `dev`, `test` o `prod`, para que nunca se aplique en `default`.
- Mapa `local.settings[env]`: CIDR (`10.10/16`, `10.20/16`, `10.30/16`), réplicas, valores por defecto de los flags y retención de logs.
- Todos los nombres llevan sufijo: `aegisvolt-reservations-${env}`, `aegisvolt-billing-${env}`, `aegisvolt-dispatch-${env}`, `aegisvolt-sagas-${env}`, `aegisvolt-feature-flags-${env}`, `aegisvolt-eks-${env}`, `/aegisvolt/${env}/<servicio>`.
- Respuesta para la defensa: la rama determina el workspace, y el workspace determina tanto la clave de estado en S3 como el sufijo de cada recurso. Por eso un apply en `test` no puede tocar `prod`.

### 3.3 Red (`modules/network`, `modules/vpc-endpoints`)
- Una VPC por ambiente con 2 subredes públicas y 2 privadas en 2 AZ, IGW, NAT (opcional en Floci) y tablas de ruta pública y privada.
- Security groups: `sg-eks-nodes`, `sg-vpce` (443 solo desde el CIDR de la VPC) y `sg-nlb`.
- VPCE de tipo **Gateway** para S3 y DynamoDB, asociados a las tablas de ruta privadas.
- VPCE de tipo **Interface** con `private_dns_enabled` para `execute-api`, `logs`, `monitoring` y `sts`.
- Camino de entrada: API Gateway HTTP API (v2) → **VPC Link** → NLB interno en subredes privadas → NodePort/Ingress de k3s → Service → Pod.
- Además hay una REST API **privada**, accesible solo por el VPCE `execute-api`, con resource policy `aws:SourceVpce`, para consumo interno.
- Se documenta en `docs/arquitectura.md` el recorrido del paquete, indicando qué tabla de ruta y qué SG intervienen en cada salto (pregunta 6.1.3).

### 3.4 Datos (`modules/dynamodb`): Database-per-Service
| Tabla | Dueño | Claves | Notas |
|---|---|---|---|
| `reservations-${env}` | station-reservation | PK `STATION#id`, SK `CONNECTOR#id` | `status`, `saga_id`, `version` |
| `billing-${env}` | billing-wallet | PK `FLEET#id`, SK `WALLET` o `TXN#<saga_id>#<HOLD\|REFUND>` | ledger idempotente |
| `dispatch-${env}` | energy-dispatch | PK `SESSION#id`, SK `META` o `TELEMETRY#ts` | TTL en la telemetría |
| `sagas-${env}` | orquestador | PK `saga_id` | GSI `status-updated_at`, usado por Prefect |
| `feature-flags-${env}` | compartida (solo lectura en servicios) | PK `flag_name` | se siembra con `aws_dynamodb_table_item` y `lifecycle { ignore_changes = [item] }`, para que los cambios en vivo no se reviertan |

### 3.5 EKS y plataforma
- **Clúster compartido** por restricción de RAM: `infra/shared` es un stack aparte con su propio state key (`shared/terraform.tfstate`, en el mismo bucket versionado). Crea un único `aws_eks_cluster` llamado `aegisvolt-eks` (Floci levanta un k3s), instala Argo Rollouts por Helm y exporta el kubeconfig.
- `modules/k8s-platform` (en `infra/live`, por workspace, con providers helm y kubernetes):
  - namespace `aegisvolt-${env}`;
  - `ResourceQuota` y `LimitRange` por namespace;
  - `NetworkPolicy` que niega el tráfico entre namespaces (k3s la aplica de forma nativa);
  - ConfigMap con `ENV`, nombres de tablas y endpoint de Floci.
- Respuesta para la defensa: el aislamiento en cómputo es lógico (namespace, cuota y NetworkPolicy), mientras que el estado, los datos, la red VPC y los logs están aislados por workspace. En AWS real sería un clúster por ambiente cambiando una sola variable.
- `modules/observability`: log groups por servicio y ambiente con retención, y alarmas de CloudWatch sobre `ErrorCount`.

---

## 4. Backend, SAGA y Feature Flags (25 %)

### 4.1 Microservicios (REST interno y una imagen Docker cada uno)
- **station-reservation**: `GET /stations`, `POST /reservations` (cambia `AVAILABLE→RESERVED` con condición), `POST /reservations/{saga_id}/release` (compensación).
- **billing-wallet**: `GET /wallets/{fleet}`, `POST /holds` (descuenta el saldo estimado, aplicando surge pricing si el flag está activo), `POST /holds/{saga_id}/refund` (compensación), `POST /wallets/{fleet}/topup`.
- **energy-dispatch**: `POST /sessions` (activa el cargador y falla si `SIMULATE_CHARGER_HARDWARE_FAULT` está activo o hay error simulado), `GET /sessions/{id}/telemetry`. Un simulador en background escribe lecturas de kW, kWh y SoC.
- Todos exponen `/healthz` y `/readyz`, propagan `X-Correlation-ID` y reciben `Idempotency-Key`.

### 4.2 GraphQL (`graphql-gateway`)
- **Queries**: `stations`, `station(id)`, `telemetry(sessionId)`, `wallet(fleetId)`, `sagas(status, limit)`, `saga(id)`, `featureFlags`, `environment`.
- **Mutations**: `reserveAndStartCharging(input: {fleetId, stationId, connectorId, estimatedKwh, clientRequestId})` (devuelve `SagaTransaction` con sus pasos), `topUpWallet`, `stopCharging`, `setFeatureFlag(name, enabled)` (protegida con un header de admin).
- **Subscription** (opcional): `connectorStatusChanged`.
- El SDL se exporta a `schema.graphql`, y el CI falla si hay drift.

### 4.3 Orquestador SAGA
- Máquina de estados persistida en `sagas-${env}`:
  - Camino feliz: `STARTED → STATION_RESERVED → FUNDS_HELD → CHARGING_STARTED → COMPLETED`.
  - Si falla el paso 2: `COMPENSATING → RESERVATION_RELEASED → COMPENSATED`.
  - Si falla el paso 3: `COMPENSATING → FUNDS_REFUNDED → RESERVATION_RELEASED → COMPENSATED`.
  - Si las compensaciones agotan los reintentos (tenacity con backoff): `COMPENSATION_FAILED`, que Prefect detecta.
- Cada transición se escribe **antes** de invocar el siguiente paso, con timestamp y error, para que el registro quede auditable.
- `correlation_id = saga_id` va en todos los logs.

### 4.4 Idempotencia (pregunta 6.3.2)
- La mutación se deduplica por `clientRequestId`: un mismo id devuelve la misma saga.
- Cada paso envía `Idempotency-Key = saga_id:step`.
- **Reserva**: `ConditionExpression status = AVAILABLE OR saga_id = :s`. Esto también evita la doble reserva concurrente.
- **Liberación**: solo se aplica si `saga_id = :s AND status = RESERVED`. En cualquier otro caso es un no-op que responde 200.
- **Cobro y reembolso**: `TransactWriteItems` dentro de la propia tabla de billing. Inserta `TXN#saga#HOLD` (o `#REFUND`) con `attribute_not_exists` y actualiza el saldo. Si el mensaje se procesa dos veces, la condición falla y el servicio responde éxito sin volver a mover dinero.

### 4.5 Feature Flags
- Valores por defecto por workspace en Terraform:
  - `ENABLE_DYNAMIC_SURGE_PRICING`: true en dev y test, false en prod.
  - `ENABLE_FAST_CHARGE_BOOST`.
  - `SIMULATE_CHARGER_HARDWARE_FAULT`: false en todos.
- Para cambiarlos en vivo hay dos vías: `scripts/flags.sh set test SIMULATE_CHARGER_HARDWARE_FAULT true` o la mutación `setFeatureFlag`. Los servicios releen cada 5 s, así que no hace falta redesplegar.
- Efectos de cada flag:
  - Surge pricing: multiplicador ×1.5 en horas pico.
  - Fast charge boost: habilita reservar conectores `ULTRA` (350 kW) con prioridad.
  - Simulate fault: hace fallar el paso 3.

---

## 5. Kubernetes y Canary

- Cada servicio es un `Rollout` de Argo con **1 réplica estable**. El reparto de tráfico lo hace **Traefik** (`trafficRouting.traefik` con un `TraefikService` ponderado entre los Services `-stable` y `-canary`). El 20 % es real, por peso de tráfico, aunque solo exista 1 pod canary, sin necesidad de 5 réplicas. Al promover, el pod viejo se elimina y la RAM vuelve a la base.
- Pasos del rollout: `setWeight 20 → pause 60s → analysis → setWeight 50 → pause 30s → analysis → 100`.
- `AnalysisTemplate` (proveedor **Job**): ejecuta `canary_check.py`, que consulta CloudWatch `ErrorCount/RequestCount` con la dimensión `PodTemplateHash = <canary>` (inyectada por Downward API y pasada como argumento por Argo).
  - Umbral para promover: tasa de error < 2 %, al menos 20 requests y `/readyz` respondiendo en los pods canary.
  - Si no se cumple: abort y rollback automático a la versión estable.
- Durante el análisis, un Job `load.py` genera tráfico sintético para que haya muestras.
- Demo de rollback: desplegar con `FAULT_INJECTION_RATE=0.3`, lo que provoca que el análisis falle y el rollout se revierta solo.

---

## 6. Gobernanza de Git y CI/CD (25 %)

### 6.1 Ramas y rulesets (`scripts/apply-rulesets.sh` con `gh api`; Terraform `infra/github` opcional)
- Ramas `dev` (por defecto), `test` y `prod`, cada una con estas reglas:
  - `non_fast_forward`, que bloquea el force push.
  - `deletion`.
  - `pull_request` obligatorio (0 aprobaciones, porque el trabajo es individual).
  - `required_status_checks`: `promotion-guard`, `lint-build`, `unit-tests`, `integration-tests`, `e2e-tests`, `terraform-plan`.
  - `strict` (la rama debe estar al día).
  - **Sin bypass actors**, para que el admin tampoco pueda saltarse las reglas.
- Repo **público**: los rulesets se pueden usar sin costo. El compañero se agrega como collaborator con rol *Write*.
- Demo: `git push origin test` y `git push --force origin dev` devuelven `GH013: Repository rule violations`.

### 6.2 `ci.yml` (en `pull_request` hacia dev, test o prod)
| Job | Runner | Qué hace |
|---|---|---|
| `promotion-guard` | GitHub | Si la base es `test`, exige que el head sea `dev`. Si la base es `prod`, exige que sea `test`. Si la base es `dev`, exige `feature/*` |
| `lint-build` | GitHub | ruff, `terraform fmt -check`/`validate`, tflint, `docker build` de las 4 imágenes, drift de `schema.graphql`, build del frontend |
| `unit-tests` | GitHub | pytest de la lógica de la SAGA y las compensaciones (clientes falsos), cálculo de precios y flags |
| `integration-tests` | GitHub | Floci como `services:` efímero: crea las tablas y prueba los servicios y el endpoint GraphQL contra DynamoDB |
| `e2e-tests` | GitHub | `docker compose up` del stack completo y tres escenarios: éxito, fondos insuficientes y fallo de hardware (verifica los estados en DynamoDB) |
| `terraform-plan` | self-hosted | `terraform workspace select ${{ github.base_ref }}`, `plan -out`, artifact y comentario en el PR |

- **Seguridad del self-hosted runner en un repo público.** Es crítico, porque un fork malicioso podría ejecutar código en tu PC. Medidas:
  - Todos los jobs self-hosted llevan `if: github.event.pull_request.head.repo.full_name == github.repository`, así que los PRs de forks nunca llegan a tu PC.
  - En Settings → Actions, activar *Require approval for all external contributors*.
  - Nunca usar `pull_request_target`.
  - `permissions:` mínimos en cada workflow.
  - El runner corre como un usuario de Windows sin privilegios de administrador, con label `aegisvolt-local`.
  - No hay secretos reales: las credenciales de Floci son `test/test`.

### 6.3 `cd.yml` (en `push` a dev, test o prod, que solo puede ocurrir por merge)
1. `ENV=${GITHUB_REF_NAME}`, con `concurrency: deploy-${ENV}` y GitHub Environment `${ENV}`.
2. `terraform workspace select $ENV && terraform apply -auto-approve`.
3. Build y push de las imágenes con tag `${GITHUB_SHA}` al ECR del ambiente.
4. `kustomize edit set image` en `overlays/$ENV` y luego `kubectl apply`, lo que inicia el Canary.
5. `kubectl argo rollouts status --timeout 10m` para cada servicio. Si un rollout aborta, el job falla (el rollback ya ocurrió).
6. Smoke test GraphQL contra el ambiente.

---

## 7. Observabilidad (12 %)

- **Logs**: campos `timestamp, level, service, env, version, pod_template_hash, correlation_id, saga_id, step, message`. Se escriben en stdout y en CloudWatch, en `/aegisvolt/${env}/<servicio>`.
- `scripts/trace.sh <env> <correlation_id>`: ejecuta `FilterLogEvents` sobre todos los grupos del ambiente y muestra la línea de tiempo.
- **Métricas**: namespace `AegisVolt/${env}`, con `RequestCount`, `ErrorCount`, `LatencyMs`, `SagaCompleted`, `SagaCompensated` y `OrphanSagas`.
- **Flows de Prefect** (deployments programados en `prefect.yaml`):
  1. `environment_health_flow` (cada 5 min): por ambiente, revisa `/healthz` de GraphQL, `DescribeTable` de las 5 tablas, `DescribeCluster`, el estado de los rollouts y la existencia de los log groups. El resultado se publica como tabla en un artifact.
  2. `saga_consistency_audit_flow` (cada 10 min):
     - Detecta sagas **huérfanas**: estado no terminal con más de 5 min de antigüedad, o `COMPENSATION_FAILED`.
     - Verifica consistencia cruzada: una saga `COMPENSATED` debe tener `TXN#REFUND` (si tuvo hold) y su conector debe estar `AVAILABLE`; una saga `COMPLETED` debe tener sesión.
     - Publica artifacts en Markdown y tabla, y `PutMetricData`.
  3. `trace_saga_flow(correlation_id, env)`: reconstruye la traza desde CloudWatch.

---

## 8. Riesgos de Floci y alternativas (se validan el día 1 con un spike)

| Riesgo | Validación | Alternativa |
|---|---|---|
| EKS→k3s inestable o sin kubeconfig usable | `terraform apply` del módulo eks + `kubectl get nodes` | k3d gestionado con `null_resource`, manteniendo `aws_eks_cluster` como recurso declarado |
| VPC Endpoints, VPC Link o NLB no soportados | `apply` del módulo network/vpce | Mantener la declaración (con `count` controlado por flag) y documentar el camino real en AWS |
| El data plane de API Gateway no llega a k3s | `curl` al stage → pod | Integración `HTTP_PROXY` directa al puerto expuesto del ingress de k3s |
| k3s no puede hacer pull desde el ECR de Floci | `kubectl run` con la imagen | `docker save` + `ctr images import` en el contenedor k3s |
| RAM insuficiente para 3 k3s | **Resuelto**: 16 GB con ~4 GB libres | **Decidido**: un solo clúster con namespaces `aegisvolt-{env}` (sección 3.5) |
| Argo Rollouts y Traefik de k3s no se integran bien | Rollout de prueba al 20 % | Volver al reparto por réplicas (1 de 5 = 20 %) **solo en el ambiente que se despliega** y reducir los otros a 1 réplica |
| Floci no persiste entre reinicios | reiniciar el contenedor | Montar volumen y fijar versión. `make rebuild-env` reconstruye a partir del tfstate |

---

## 9. Cronograma (5 días: lunes 16 a viernes 20 de nov.; defensa el sábado 21)

Con 5 días, el orden de trabajo sigue el peso de cada capa en la rúbrica. Cada día termina con algo demostrable y con commit vía PR a `dev`. Lo marcado **(opcional)** solo se hace si sobra tiempo.

| Día | Mañana | Tarde | Al cierre del día debe funcionar… |
|---|---|---|---|
| **Lun 16** | Crear el repo en GitHub (público o con Pro), las ramas `dev`, `test` y `prod`, y los rulesets (script `gh api`). Levantar `docker-compose` con Floci y Prefect. **Spike de Floci** de 2 h: EKS→k3s, VPCE, API Gateway→k3s, ECR pull y persistencia; se eligen las alternativas de la sección 8. | `infra/bootstrap` (bucket versionado y tabla de locks), backend S3, workspaces y módulos `network`, `vpc-endpoints`, `dynamodb` y `feature-flags`. **Se entrega `schema.graphql` al compañero.** | Bloqueo de `git push` y `--force`; `terraform apply` en los 3 workspaces; 15 tablas con sufijo de ambiente; versiones del tfstate en S3 |
| **Mar 17** | `aegis_common` (logging JSON, flags, métricas) y los 3 microservicios con unit tests | Orquestador SAGA, compensaciones, idempotencia y gateway GraphQL; e2e local con `docker compose` | Demo de SAGA fallida → `COMPENSATED` en DynamoDB activando el flag en `test` |
| **Mié 18** | Módulos `eks`, `ecr`, `api-gateway`, `observability` y `k8s-platform` (Argo Rollouts). Dockerfiles y overlays de Kustomize | Rollouts + AnalysisTemplate + `canary_check.py` + `load.py`; primer deploy a `dev` en k3s | Canary al 20 % → análisis → 100 %, y rollback automático con `FAULT_INJECTION_RATE` |
| **Jue 19** | `ci.yml` (promotion-guard, lint-build, unit, integration, e2e, terraform-plan) y self-hosted runner | `cd.yml` (workspace dinámico, apply, build/push, rollout); logs en CloudWatch y `trace.sh` | El PR muestra todos los checks en verde y el merge despliega solo el ambiente destino |
| **Vie 20** | Flows de Prefect (health y audit) con deployments programados; integración con el frontend del compañero | **Promoción real** `feature→dev→test→prod` por PRs; ensayo completo del runbook (sección 11); `docs/runbook-defensa.md` y diagrama | Los 8 pasos de la sección 11 salen sin errores en los 3 ambientes |
| **Sáb 21** | Defensa. No se toca código. Solo `docker compose up` y verificar que los ambientes están vivos 1 h antes | | |

**Recortes para caber en 5 días** (no afectan ningún criterio de la rúbrica):
- Los rulesets se crean con un script `scripts/apply-rulesets.sh` (`gh api`) en lugar del provider de Terraform para GitHub. Este pasa a ser **(opcional)**.
- **(Opcional)**: la subscription GraphQL (el frontend usa polling), la REST API privada adicional, el NAT gateway, el flow `trace_saga_flow` (lo cubre `trace.sh`), Playwright y los ADRs.
- Ya está decidido usar un solo clúster k3s con namespaces por ambiente. El spike del lunes solo valida que el EKS de Floci arranque un k3s y genere un kubeconfig usable.
- **Regla de corte**: si un bloque se retrasa más de medio día, se aplica su alternativa de la sección 8 y se sigue. No se depura Floci más allá de 1 h por problema.

---

## 10. Frontend — responsabilidad del compañero

**Contrato**
- Usar `services/graphql-gateway/schema.graphql`, que estará disponible desde el **lunes 16 por la tarde**.
- Endpoint por ambiente vía `VITE_GRAPHQL_URL` (o equivalente), por ejemplo `http://localhost:<puerto-apigw>/{env}/graphql`.
- WSS opcional para `connectorStatusChanged`. Si no se usa, hacer polling cada 2–3 s.

**Stack**: libre. Se sugiere React + Vite + TypeScript + Apollo Client (o urql), con graphql-codegen para tipar a partir del SDL.

**Pantallas mínimas**
1. **Estado de electrolineras**: lista o mapa de estaciones y conectores con su estado (`AVAILABLE`, `RESERVED`, `CHARGING`, `FAULT`) en tiempo real y la telemetría de las sesiones activas.
2. **Reservar y activar carga**: formulario que dispara `reserveAndStartCharging` y muestra el avance de la saga paso a paso, incluida la compensación si ocurre.
3. **Feature flags**: query `featureFlags` + `environment`. Muestra un badge con el ambiente activo y el estado de cada flag, que debe reflejar los cambios sin recargar ni redesplegar.
4. **Historial de transacciones**: `sagas(status)` con filtros (completadas, compensadas, fallidas), detalle de pasos, errores y `correlation_id` copiable.

**Integración con el CI** (dentro de `frontend/`)
- Scripts `npm run lint`, `npm run build` y `npm test`, que se ejecutan en el job `lint-build`.
- `Dockerfile` (build estático servido por nginx), desplegado como Deployment en cada ambiente por `cd.yml`.
- Opcional: smoke test con Playwright incluido en `e2e-tests`.
- **Calendario del compañero**:
  - **Lunes y martes**: trabaja contra mocks del schema (`@graphql-tools/mock` o MSW).
  - **Miércoles**: conecta al stack real con `docker compose up`, que estará disponible desde el martes por la noche.
  - **Jueves**: entrega el `Dockerfile` y los scripts npm para el CI.
  - **Viernes por la mañana**: integración final con los 3 ambientes.

**Nota**: la sustentación es individual, así que conviene repasar con el compañero cómo el frontend consume GraphQL y cómo refleja los flags (8 % de la nota).

---

## 11. Verificación de punta a punta (= runbook de la defensa)

1. `docker compose up -d` y luego `terraform workspace select dev|test|prod && terraform apply` en cada ambiente. Comprobar con `aws dynamodb list-tables --endpoint-url http://localhost:4566` que existen 15 tablas con sufijos distintos.
2. `aws s3api list-object-versions --bucket aegisvolt-tfstate --prefix env:/dev/` debe mostrar varias versiones. Luego ensayar `restore-tfstate.sh dev <version>`.
3. Ejecutar `flags.sh set test SIMULATE_CHARGER_HARDWARE_FAULT true` y la mutación `reserveAndStartCharging` en test. Comprobar:
   - la saga queda en `COMPENSATED`;
   - existe `TXN#<saga>#REFUND` y el saldo se restauró;
   - el conector vuelve a `AVAILABLE`;
   - prod sigue intacto.
4. Repetir la mutación de compensación: no aparecen asientos duplicados (idempotencia).
5. `trace.sh test <saga_id>` muestra los logs de los 3 servicios. En la UI de Prefect (:4200), el audit flow reporta la saga compensada.
6. `git push origin test` y `git push --force origin dev` son rechazados. Un PR de `feature/x` hacia `test` falla en `promotion-guard`.
7. Merge a dev: el CD aplica solo el workspace dev y hace el Canary al 20 % → análisis → 100 %. Con una versión con `FAULT_INJECTION_RATE=0.3`, el rollback es automático.
8. Cambiar un flag en dev: el frontend de dev cambia sin redeploy y el de prod no.
