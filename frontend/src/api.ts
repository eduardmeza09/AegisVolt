// Cliente GraphQL mínimo (fetch) + operaciones del contrato services/graphql_gateway/schema.graphql.

/**
 * Detrás del API Gateway la app vive en  .../<stage>/_user_request_/web/
 * y GraphQL en                           .../<stage>/_user_request_/graphql
 * => mismo origen, sin CORS y cada ambiente habla con SU propio backend.
 */
export function resolveGraphqlUrl(pathname: string, override?: string): string {
  if (override) return override;
  const i = pathname.lastIndexOf("/web");
  const base = i >= 0 ? pathname.slice(0, i) : "";
  return `${base}/graphql`;
}

const GRAPHQL_URL = resolveGraphqlUrl(window.location.pathname, import.meta.env.VITE_GRAPHQL_URL);

export class GraphqlError extends Error {}

export async function gql<T>(query: string, variables?: Record<string, unknown>, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(GRAPHQL_URL, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) throw new GraphqlError(`HTTP ${res.status}`);
  const body = await res.json();
  if (body.errors?.length) throw new GraphqlError(body.errors.map((e: { message: string }) => e.message).join("; "));
  return body.data as T;
}

export const Q = {
  overview: `query {
    environment { name version podTemplateHash }
    stations { stationId name city availableConnectors
      connectors { connectorId connectorType powerKw status sagaId fleetId } }
    chargingSessions(status: "CHARGING", limit: 10) {
      sessionId stationId connectorId fleetId kwhDelivered estimatedKwh powerKwNow socPercent }
  }`,
  flags: `query { environment { name } featureFlags { name enabled description updatedAt updatedBy } }`,
  fleets: `query { fleets { fleetId fleetName balance currency } }`,
  quote: `query($t: String!, $k: Float!) { priceQuote(connectorType: $t, kwh: $k) {
    pricePerKwh surgeApplied surgeMultiplier total } }`,
  sagas: `query($s: SagaStatus, $l: Int!) { sagas(status: $s, limit: $l) {
    sagaId correlationId status env fleetId stationId connectorId estimatedKwh amount surgeApplied
    errorCode errorMessage failedStep createdAt updatedAt
    steps { name service status detail at idempotentReplay } } }`,
  saga: `query($id: String!) { saga(sagaId: $id) {
    sagaId correlationId status env fleetId stationId connectorId estimatedKwh amount surgeApplied
    errorCode errorMessage failedStep createdAt updatedAt
    steps { name service status detail at idempotentReplay } } }`,
  telemetry: `query($id: String!) { telemetry(sessionId: $id, limit: 24) { timestamp powerKw kwhDelivered socPercent } }`,
  reserve: `mutation($input: ReserveAndStartChargingInput!) { reserveAndStartCharging(input: $input) {
    sagaId correlationId status amount surgeApplied errorCode errorMessage failedStep
    steps { name service status detail at idempotentReplay } } }`,
  stop: `mutation($id: String!) { stopCharging(sagaId: $id) { sagaId status } }`,
  retry: `mutation($id: String!) { retryCompensation(sagaId: $id) { sagaId status
    steps { name service status detail at idempotentReplay } } }`,
  setFlag: `mutation($n: String!, $e: Boolean!) { setFeatureFlag(name: $n, enabled: $e) { name enabled } }`,
};
