// Utilidades puras (cubiertas por src/lib.test.ts).
import type { SagaStatus, SagaStep } from "./types";

export type Tone = "ok" | "warn" | "bad" | "info" | "muted";

export function sagaTone(status: SagaStatus): Tone {
  switch (status) {
    case "COMPLETED":
    case "FINISHED":
      return "ok";
    case "COMPENSATED":
      return "warn";
    case "FAILED":
    case "COMPENSATION_FAILED":
      return "bad";
    default:
      return "info";
  }
}

export const SAGA_LABEL: Record<SagaStatus, string> = {
  STARTED: "Iniciada",
  STATION_RESERVED: "Conector reservado",
  FUNDS_HELD: "Saldo retenido",
  COMPENSATING: "Compensando",
  FUNDS_REFUNDED: "Saldo reembolsado",
  RESERVATION_RELEASED: "Conector liberado",
  COMPLETED: "Cargando",
  FINISHED: "Finalizada",
  COMPENSATED: "Compensada",
  FAILED: "Fallida",
  COMPENSATION_FAILED: "Compensación fallida",
};

export const STEP_LABEL: Record<string, string> = {
  RESERVE_CONNECTOR: "Reservar conector",
  HOLD_FUNDS: "Retener saldo",
  START_CHARGING: "Activar cargador",
  COMPENSATE_REFUND: "Reembolsar saldo",
  COMPENSATE_RELEASE: "Liberar conector",
  COMPENSATE_REFUND_REPLAY: "Reembolso (reintento)",
  COMPENSATE_RELEASE_REPLAY: "Liberación (reintento)",
  STOP_CHARGING: "Detener carga",
  COMPENSATION: "Compensación",
};

export const ERROR_LABEL: Record<string, string> = {
  HARDWARE_FAULT: "Fallo físico del cargador",
  INSUFFICIENT_FUNDS: "Fondos insuficientes",
  CONNECTOR_UNAVAILABLE: "Conector no disponible",
  FAST_CHARGE_DISABLED: "Ultra-carga deshabilitada",
};

export function stepTone(step: Pick<SagaStep, "status">): Tone {
  if (step.status === "SUCCEEDED") return "ok";
  if (step.status === "COMPENSATED") return "warn";
  if (step.status === "FAILED") return "bad";
  return "muted";
}

/** Pasos que se muestran en el stepper: los 3 de avance + las compensaciones que hubo. */
export function plannedSteps(steps: SagaStep[]): { name: string; step?: SagaStep }[] {
  const forward = ["RESERVE_CONNECTOR", "HOLD_FUNDS", "START_CHARGING"];
  const byName = new Map(steps.map((s) => [s.name, s]));
  const out: { name: string; step?: SagaStep }[] = forward.map((name) => ({ name, step: byName.get(name) }));
  for (const s of steps) if (!forward.includes(s.name)) out.push({ name: s.name, step: s });
  return out;
}

export function money(value: number | null | undefined, currency = "USD"): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("es-CO", { style: "currency", currency, minimumFractionDigits: 2 }).format(value);
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return new Date(iso).toLocaleDateString("es-CO");
}

export function shortId(id: string): string {
  return id.length > 13 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}
