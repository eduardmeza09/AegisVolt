# Frontend web

Aplicación React 18 + Vite + TypeScript ubicada en [`frontend/`](../frontend). El diseño sigue la referencia visual del proyecto: fondo oscuro, acento cian neón, títulos con la fuente ancha Syncopate y el "ELECTRIC" gigante de fondo. Las fotos del vehículo (`frontend/public/img/car-{black,blue,grey}[-sm].webp`) se generaron con IA y se retocaron con `scripts/retouch_car_images.py` para **quitar los emblemas de marca** (capó y tapas de rueda). El script también las recorta y las exporta a WebP en 1800 px y 900 px, servidas con `srcset`. El fondo negro se funde con el sitio mediante una máscara CSS elíptica. El cargador también es una imagen generada con IA, sin marcas (`public/img/charger-hero.webp` para el encabezado y `charger.webp` para las tarjetas). En cada tarjeta de estación se muestra encendido si hay una carga activa en esa estación y desaturado si no.

La variante del auto cambia según el estado:
- **Reserva:** negro antes de enviar, azul con luces si la SAGA completa y gris apagado si se compensa o falla.
- **Flags:** azul si están activos (negro con luces para el flag de fallo) y gris si están inactivos.

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

## Tests E2E desde el navegador

`frontend/e2e/saga.spec.ts` (Playwright) opera la UI como un usuario:
- **Carga:** comprueba que se muestran el ambiente, las estaciones y los 3 flags.
- **Éxito:** clic en un conector, reserva y resultado "Cargando"; después detiene la carga desde el historial y el estado pasa a "Finalizada".
- **Fondos insuficientes:** con `fleet-sinfondos` el resultado es "Compensada" y solo se libera el conector.
- **Fallo de hardware:** activa el flag desde el **modo administrador de la UI**; el resultado es "Compensada", con reembolso y liberación, y el **reintento** queda marcado como idempotente. Al final apaga el flag.

```bash
docker compose --profile app up -d --build      # frontend en http://localhost:8081/web/ (nginx.compose.conf)
cd frontend && PW_CHANNEL=msedge npx playwright test
# contra un ambiente desplegado:
E2E_BASE_URL=$(terraform -chdir=../infra/live output -raw frontend_url) ADMIN_TOKEN=$(terraform -chdir=../infra/live output -raw admin_token) PW_CHANNEL=msedge npx playwright test
```

## CI/CD

- `ci.yml`, job `lint-build`: `npm ci`, typecheck (`tsc`), tests (vitest), `vite build` y `docker build` de la imagen nginx.
- `scripts/deploy.sh`: construye `aegisvolt/frontend:<sha>`, la importa en k3s y espera el `rollout status` del Deployment.
- `ci.yml`, job `e2e-tests`: después del E2E por API corre el E2E de navegador (Chromium) contra el stack de compose.
- `cd.yml`: smoke test del `frontend_url` y, en dev y test, el E2E de navegador contra el ambiente desplegado (Edge del runner).
