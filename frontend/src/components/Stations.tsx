import { useEffect, useState } from "react";
import { gql, Q } from "../api";
import { timeAgo } from "../lib";
import type { ChargingSession, Connector, Station, Telemetry } from "../types";

const STATUS_LABEL: Record<string, string> = {
  AVAILABLE: "Disponible",
  RESERVED: "Reservado",
  CHARGING: "Cargando",
  FAULT: "Falla",
};

interface Props {
  stations: Station[];
  sessions: ChargingSession[];
  updatedAt: number | null;
  error: string | null;
  onPick: (stationId: string, connector: Connector) => void;
}

function Sparkline({ sessionId }: { sessionId: string }) {
  const [points, setPoints] = useState<Telemetry[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () =>
      gql<{ telemetry: Telemetry[] }>(Q.telemetry, { id: sessionId })
        .then((d) => alive && setPoints(d.telemetry))
        .catch(() => undefined);
    load();
    const t = window.setInterval(load, 5000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [sessionId]);
  if (points.length < 2) return <div className="spark empty">esperando telemetría…</div>;
  const max = Math.max(...points.map((p) => p.powerKw), 1);
  const d = points.map((p, i) => `${(i / (points.length - 1)) * 100},${30 - (p.powerKw / max) * 26}`).join(" ");
  return (
    <svg className="spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-label="Potencia (kW)">
      <polyline points={d} fill="none" stroke="#36d6f5" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function Stations({ stations, sessions, updatedAt, error, onPick }: Props) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <section className="section" id="estaciones">
      <div className="section-head">
        <h2 className="title">
          Estaciones <em>en tiempo real</em>
        </h2>
        <span className={`pill ${error ? "bad" : ""}`}>{error ? "sin conexión" : `actualizado ${timeAgo(updatedAt ? new Date(updatedAt).toISOString() : null)}`}</span>
      </div>

      <div className="grid-2">
        {stations.map((st) => {
          const charging = st.connectors.some((c) => c.status === "CHARGING");
          return (
            <article className="card station" key={st.stationId}>
              <div className="station-body">
                <h3>{st.name}</h3>
                <p className="muted">
                  {st.city} · {st.availableConnectors}/{st.connectors.length} libres
                </p>
                <ul className="connectors">
                  {st.connectors.map((c) => (
                    <li key={c.connectorId}>
                      <button
                        type="button"
                        className={`conn conn-${c.status.toLowerCase()}`}
                        disabled={c.status !== "AVAILABLE"}
                        onClick={() => onPick(st.stationId, c)}
                        title={c.status === "AVAILABLE" ? "Reservar este conector" : `${STATUS_LABEL[c.status]}${c.fleetId ? ` · ${c.fleetId}` : ""}`}
                      >
                        <b>{c.connectorId.toUpperCase()}</b>
                        <span>
                          {c.connectorType} · {c.powerKw} kW
                        </span>
                        <i>{STATUS_LABEL[c.status]}</i>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
              <img className={`station-art ${charging ? "on" : "off"}`} src="./img/charger.webp" width={275} height={490}
                alt={charging ? "Cargador entregando energía" : "Cargador en espera"} loading="lazy" decoding="async" />
            </article>
          );
        })}
      </div>

      {sessions.length > 0 && (
        <div className="sessions">
          <h3 className="subtitle">Sesiones activas · telemetría</h3>
          <div className="grid-3">
            {sessions.map((s) => {
              const pct = s.estimatedKwh ? Math.min(100, (s.kwhDelivered / s.estimatedKwh) * 100) : 0;
              return (
                <div className="card session" key={s.sessionId}>
                  <div className="session-top">
                    <b>
                      {s.stationId} / {s.connectorId?.toUpperCase()}
                    </b>
                    <span className="muted">{s.fleetId}</span>
                  </div>
                  <Sparkline sessionId={s.sessionId} />
                  <div className="bar">
                    <span style={{ width: `${pct}%` }} />
                  </div>
                  <div className="session-meta">
                    <span>
                      {s.kwhDelivered.toFixed(1)} / {s.estimatedKwh} kWh
                    </span>
                    <span>{s.powerKwNow.toFixed(0)} kW</span>
                    <span>SoC {s.socPercent.toFixed(0)}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
