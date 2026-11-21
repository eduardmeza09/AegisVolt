# Traspaso para el frontend

El backend, la infraestructura y el CI/CD están listos. Este documento reúne lo que el frontend necesita para conectarse.

## Endpoint GraphQL por ambiente

El endpoint de cada ambiente es la URL del API Gateway en Floci:

```bash
cd infra/live && terraform workspace select dev && terraform output -raw graphql_url
# http://localhost:4566/restapis/<apiId>/dev/_user_request_/graphql
```

Configúralo como variable de build (por ejemplo `VITE_GRAPHQL_URL`), con una URL distinta para dev, test y prod. La query `environment { name }` devuelve el ambiente real al que está conectado el frontend; sirve para mostrar el badge.

Para desarrollo sin Kubernetes, levanta `docker compose --profile app up -d` y usa `http://localhost:8080/graphql`.

CORS está abierto (`*`). No hay WebSockets: el "tiempo real" se hace con **polling cada 2 o 3 s**. La telemetría avanza cada 5 s.

## Contrato

El contrato es [`services/graphql_gateway/schema.graphql`](../services/graphql_gateway/schema.graphql). El CI falla si este archivo y el código no coinciden. Se puede generar el tipado con graphql-codegen.

| Pantalla requerida | Operaciones |
|---|---|
| 1. Estado de electrolineras | `stations { stationId name city lat lng availableConnectors connectors { connectorId connectorType powerKw status sagaId } }` · `chargingSessions(status:"CHARGING")` · `telemetry(sessionId)` |
| 2. Reservar y activar carga | `fleets { fleetId fleetName balance }` · `priceQuote(connectorType, kwh)` · `reserveAndStartCharging(input:{fleetId, stationId, connectorId, estimatedKwh, clientRequestId})` · `stopCharging(sagaId)` |
| 3. Feature flags | `environment { name version }` · `featureFlags { name enabled description updatedAt updatedBy }` |
| 4. Historial y compensaciones | `sagas(status, limit) { sagaId correlationId status errorCode failedStep amount surgeApplied steps { name service status detail at idempotentReplay } createdAt }` · `saga(sagaId)` · `retryCompensation(sagaId)` |

Notas:
- `reserveAndStartCharging` **siempre** devuelve la saga, también cuando falla. El resultado está en `status`, que puede ser `COMPLETED`, `COMPENSATED` o `FAILED`, y en `errorCode`, que puede ser `HARDWARE_FAULT`, `INSUFFICIENT_FUNDS`, `CONNECTOR_UNAVAILABLE` o `FAST_CHARGE_DISABLED`. Cada paso aparece en `steps`, en orden.
- Envía un `clientRequestId` nuevo (uuid) por cada intento del usuario. Si llega dos veces el mismo, el backend no cobra dos veces.
- `setFeatureFlag` requiere el header `x-admin-token` (`terraform output -raw admin_token`). Es opcional en la UI; los flags también se cambian con `scripts/flags.sh`.
- Flotas de demo:
  - `fleet-rapido` (saldo alto).
  - `fleet-andina`.
  - `fleet-sinfondos`: provoca `INSUFFICIENT_FUNDS`, que compensa la reserva.
- Conectores `ULTRA`: solo se pueden reservar si `ENABLE_FAST_CHARGE_BOOST` está activa. En prod está desactivada.

## Integración con el CI

El job `lint-build` de `ci.yml` ya intenta compilar `frontend/` si existe `frontend/package.json`: ejecuta `npm ci`, `npm run lint` (si existe) y `npm run build`.
