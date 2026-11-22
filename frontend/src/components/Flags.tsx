import { useState } from "react";
import { gql, Q } from "../api";
import { CarPhoto } from "../art/CarPhoto";
import { useLocalStorage, usePoll } from "../hooks";
import { timeAgo } from "../lib";
import type { Environment, FeatureFlag } from "../types";

const PRETTY: Record<string, [string, string]> = {
  ENABLE_DYNAMIC_SURGE_PRICING: ["Tarifa dinámica", "×1.5 en horas pico"],
  ENABLE_FAST_CHARGE_BOOST: ["Ultra-carga", "Reserva prioritaria 350 kW"],
  SIMULATE_CHARGER_HARDWARE_FAULT: ["Fallo de hardware", "Inyección de fallos → rollback SAGA"],
};

export function Flags() {
  const { data, error, refresh } = usePoll<{ environment: Environment; featureFlags: FeatureFlag[] }>(Q.flags, 3000);
  const [token, setToken] = useLocalStorage("aegisvolt-admin-token", "");
  const [admin, setAdmin] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const env = data?.environment.name ?? "…";
  const flags = data?.featureFlags ?? [];
  const order = ["ENABLE_DYNAMIC_SURGE_PRICING", "SIMULATE_CHARGER_HARDWARE_FAULT", "ENABLE_FAST_CHARGE_BOOST"];
  const sorted = [...flags].sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));

  async function toggle(f: FeatureFlag) {
    setMsg(null);
    try {
      await gql(Q.setFlag, { n: f.name, e: !f.enabled }, { "x-admin-token": token });
      setMsg(`${f.name} = ${!f.enabled} en ${env} (sin redespliegue)`);
      refresh();
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  return (
    <section className="section flags" id="flags">
      <h2 className="title center">
        Feature flags
        <br />
        <em>ambiente {env}</em>
      </h2>
      <div className="flag-row">
        {sorted.map((f, i) => {
          const [label, hint] = PRETTY[f.name] ?? [f.name, f.description];
          const danger = f.name === "SIMULATE_CHARGER_HARDWARE_FAULT";
          return (
            <article key={f.name} className={`flag ${f.enabled ? "on" : "off"} ${danger ? "danger" : ""} ${i === 1 ? "mid" : ""}`}>
              <CarPhoto paint={f.enabled ? (danger ? "black" : "blue") : "grey"} sizes="(max-width: 680px) 90vw, 30vw" />
              <h3>{label}</h3>
              <p className="muted">{hint}</p>
              <div className="flag-state">
                <span className={`switch ${f.enabled ? "on" : ""}`} aria-hidden />
                <b>{f.enabled ? "ACTIVO" : "INACTIVO"}</b>
              </div>
              <code>{f.name}</code>
              <small className="muted">
                {f.updatedBy ?? "terraform"} · {timeAgo(f.updatedAt)}
              </small>
              {admin && (
                <button type="button" className="btn ghost" onClick={() => toggle(f)}>
                  {f.enabled ? "Desactivar" : "Activar"}
                </button>
              )}
            </article>
          );
        })}
      </div>
      <p className="lead center">
        Estado leído de <code>aegisvolt-feature-flags-{env}</code> cada 3 s. Cada ambiente tiene su propia tabla: cambiar
        un flag aquí no afecta a los demás ni requiere redesplegar.
      </p>
      {error && <p className="hint bad center">{error}</p>}
      <div className="admin">
        {admin ? (
          <>
            <input type="password" placeholder="x-admin-token (terraform output admin_token)" value={token}
              onChange={(e) => setToken(e.target.value)} />
            <button type="button" className="btn ghost" onClick={() => setAdmin(false)}>Cerrar</button>
          </>
        ) : (
          <button type="button" className="btn" onClick={() => setAdmin(true)}>Modo administrador</button>
        )}
      </div>
      {msg && <p className="hint center">{msg}</p>}
    </section>
  );
}
