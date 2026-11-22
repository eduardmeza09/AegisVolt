import { Bolt, Check, Cross, Plug, Shield, Undo } from "../art/icons";
import { plannedSteps, STEP_LABEL, stepTone } from "../lib";
import type { SagaStep } from "../types";

const ICON: Record<string, () => JSX.Element> = {
  RESERVE_CONNECTOR: Plug,
  HOLD_FUNDS: Shield,
  START_CHARGING: Bolt,
};

const HINT: Record<string, string> = {
  RESERVE_CONNECTOR: "station-reservation cambia el conector a RESERVED en su tabla DynamoDB.",
  HOLD_FUNDS: "billing-wallet descuenta el saldo estimado de la billetera de la flota.",
  START_CHARGING: "energy-dispatch ordena al cargador iniciar el flujo eléctrico.",
  COMPENSATE_REFUND: "Compensación: billing-wallet reembolsa exactamente lo retenido.",
  COMPENSATE_RELEASE: "Compensación: station-reservation devuelve el conector a AVAILABLE.",
};

/** Lista de pasos de la SAGA (pendiente / ok / fallido / compensado). */
export function SagaSteps({ steps, running }: { steps: SagaStep[]; running?: boolean }) {
  return (
    <ol className="steps">
      {plannedSteps(steps).map(({ name, step }, i) => {
        const tone = step ? stepTone(step) : running && i === steps.length ? "info" : "muted";
        const Icon = step?.status === "FAILED" ? Cross : step?.status === "COMPENSATED" ? Undo
          : step?.status === "SUCCEEDED" ? Check : ICON[name] ?? Undo;
        return (
          <li key={name} className={`step tone-${tone}`}>
            <span className="step-icon">
              <Icon />
            </span>
            <div>
              <h4>
                {STEP_LABEL[name] ?? name}
                {step?.idempotentReplay && <span className="tag">idempotente</span>}
              </h4>
              <p>{step?.detail ?? HINT[name.replace("_REPLAY", "")] ?? ""}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
