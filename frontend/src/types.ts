export type ConnectorStatus = "AVAILABLE" | "RESERVED" | "CHARGING" | "FAULT";

export type SagaStatus =
  | "STARTED" | "STATION_RESERVED" | "FUNDS_HELD" | "COMPENSATING" | "FUNDS_REFUNDED"
  | "RESERVATION_RELEASED" | "COMPLETED" | "FINISHED" | "COMPENSATED" | "FAILED" | "COMPENSATION_FAILED";

export interface Connector {
  connectorId: string;
  connectorType: string;
  powerKw: number;
  status: ConnectorStatus;
  sagaId: string | null;
  fleetId: string | null;
}

export interface Station {
  stationId: string;
  name: string;
  city: string;
  availableConnectors: number;
  connectors: Connector[];
}

export interface ChargingSession {
  sessionId: string;
  stationId: string | null;
  connectorId: string | null;
  fleetId: string | null;
  kwhDelivered: number;
  estimatedKwh: number;
  powerKwNow: number;
  socPercent: number;
}

export interface Environment {
  name: string;
  version: string;
  podTemplateHash?: string;
}

export interface FeatureFlag {
  name: string;
  enabled: boolean;
  description: string;
  updatedAt: string | null;
  updatedBy: string | null;
}

export interface Fleet {
  fleetId: string;
  fleetName: string;
  balance: number;
  currency: string;
}

export interface Quote {
  pricePerKwh: number;
  surgeApplied: boolean;
  surgeMultiplier: number;
  total: number;
}

export interface SagaStep {
  name: string;
  service: string;
  status: string;
  detail: string | null;
  at: string | null;
  idempotentReplay: boolean | null;
}

export interface Saga {
  sagaId: string;
  correlationId: string;
  status: SagaStatus;
  env?: string;
  fleetId?: string;
  stationId?: string;
  connectorId?: string;
  estimatedKwh?: number;
  amount: number | null;
  surgeApplied: boolean | null;
  errorCode: string | null;
  errorMessage: string | null;
  failedStep: string | null;
  createdAt?: string;
  steps: SagaStep[];
}

export interface Telemetry {
  timestamp: string;
  powerKw: number;
  kwhDelivered: number;
  socPercent: number;
}
