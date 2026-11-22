# Frontend web

Aplicación React 18 + Vite + TypeScript ubicada en [`frontend/`](../frontend). El diseño sigue la referencia visual del proyecto: fondo oscuro, acento cian neón, títulos con la fuente ancha Syncopate y el "ELECTRIC" gigante de fondo. Las ilustraciones son SVG propios (`src/art/`): un auto con variantes blanca, oscura y azul, y un cargador.

## Cómo se conecta a cada ambiente

El frontend corre como un nginx en el namespace de cada ambiente y se publica en el **mismo API Gateway** que GraphQL:

```
.../restapis/<api>/<env>/_user_request_/web/      -> frontend (nginx, namespace aegisvolt-<env>)
.../restapis/<api>/<env>/_user_request_/graphql   -> graphql-gateway
```

`src/api.ts` deriva el endpoint GraphQL a partir de la URL de la página. Esto tiene tres consecuencias:
- La **misma imagen** sirve para dev, test y prod, y se promueve sin recompilar.
- El navegador nunca habla con el backend de otro ambiente.
- No hay CORS, porque todo es mismo origen.

```bash
cd infra/live && terraform workspace select dev && terraform output -raw frontend_url
```

Rutas involucradas:
- **API Gateway** (`infra/modules/api-gateway`): `ANY /web`, `ANY /web/` y `ANY /web/{proxy+}`, que van a Traefik en `/<env>/web/...`.
- **Traefik** (`k8s/overlays/<env>/routes.yaml`): quita el prefijo `/<env>/web` y envía el tráfico al Service `frontend` (`k8s/base/frontend.yaml`).

## Funcionalidades (sección 2.1 de la especificación)

| Requisito | Sección de la UI | Datos |
|---|---|---|
| 1. Estado de electrolineras y conectores en tiempo real | "Estaciones en tiempo real" + "Sesiones activas" | `stations`, `chargingSessions`, `telemetry` (polling cada 3 s; telemetría cada 5 s) |
| 2. Reserva y activación (dispara la SAGA) | "Reserva y activa tu carga" | `fleets`, `priceQuote`, `reserveAndStartCharging`. Muestra cada paso y las compensaciones |
| 3. Feature Flags por ambiente | "Feature flags · ambiente X" + badge del header | `environment`, `featureFlags` (cada 3 s). Modo administrador opcional con `setFeatureFlag` + `x-admin-token` |
| 4. Historial y compensaciones | "Historial de transacciones" | `sagas(status)`, `saga(id)`, `retryCompensation`, `stopCharging`; búsqueda por `correlation_id` en el footer |

Comportamientos de la interfaz:
- Al hacer clic en un conector **Disponible** del panel, queda preseleccionado en el formulario de reserva.
- Si el saldo de la flota no alcanza, el formulario lo advierte antes de enviar. Con `fleet-sinfondos` se demuestra la compensación del paso 2.
- Cada intento envía un `clientRequestId` nuevo, así que un doble clic no cobra dos veces.
- El badge del header cambia de color según el ambiente: cian en dev, ámbar en test y verde en prod.

## Desarrollo local

```bash
cd frontend
npm ci
npm run dev                         # http://localhost:5173 ; /graphql -> http://localhost:8080 (docker compose --profile app)
VITE_GRAPHQL_URL=$(cd ../infra/live && terraform output -raw graphql_url) npm run dev   # contra un ambiente real
npm run lint && npm test && npm run build
```

## CI/CD

- `ci.yml`, job `lint-build`: `npm ci`, typecheck (`tsc`), tests (vitest), `vite build` y `docker build` de la imagen nginx.
- `scripts/deploy.sh`: construye `aegisvolt/frontend:<sha>`, la importa en k3s y espera el `rollout status` del Deployment.
- `cd.yml`: después del deploy, un smoke test comprueba que el `frontend_url` del ambiente responde.
