import { useEffect, useMemo, useState } from "react";
import { gql, Q } from "../api";
import { Car } from "../art/Car";
import { usePoll } from "../hooks";
import { ERROR_LABEL, money, SAGA_LABEL, sagaTone } from "../lib";
import type { Fleet, Quote, Saga, Station } from "../types";
import { SagaSteps } from "./SagaSteps";

interface Props {
  stations: Station[];
  pick: { stationId: string; connectorId: string } | null;
  onDone: () => void;
}

export function Reserve({ stations, pick, onDone }: Props) {
  const fleets = usePoll<{ fleets: Fleet[] }>(Q.fleets, 5000);
  const [fleetId, setFleetId] = useState("fleet-rapido");
  const [stationId, setStationId] = useState("");
  const [connectorId, setConnectorId] = useState("");
  const [kwh, setKwh] = useState(30);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const [saga, setSaga] = useState<Saga | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (pick) {
      setStationId(pick.stationId);
      setConnectorId(pick.connectorId);
    }
  }, [pick]);

  const station = stations.find((s) => s.stationId === stationId) ?? stations[0];
  const available = useMemo(() => station?.connectors.filter((c) => c.status === "AVAILABLE") ?? [], [station]);
  const connector = available.find((c) => c.connectorId === connectorId) ?? available[0];

  useEffect(() => {
    if (!connector) return setQuote(null);
    gql<{ priceQuote: Quote }>(Q.quote, { t: connector.connectorType, k: kwh })
      .then((d) => setQuote(d.priceQuote))
      .catch(() => setQuote(null));
  }, [connector?.connectorType, kwh]); // eslint-disable-line react-hooks/exhaustive-deps

  const fleet = fleets.data?.fleets.find((f) => f.fleetId === fleetId);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!station || !connector) return;
    setBusy(true);
    setError(null);
    setSaga(null);
    try {
      const d = await gql<{ reserveAndStartCharging: Saga }>(Q.reserve, {
        input: {
          fleetId,
          stationId: station.stationId,
          connectorId: connector.connectorId,
          estimatedKwh: kwh,
          clientRequestId: crypto.randomUUID(),
        },
      });
      setSaga(d.reserveAndStartCharging);
      fleets.refresh();
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="section" id="reservar">
      <h2 className="title center">
        Reserva y activa <em>tu carga</em>
      </h2>
      <p className="lead center">Cada reserva dispara una SAGA orquestada sobre tres microservicios.</p>

      <div className="reserve">
        <div className="reserve-art">
          <Car variant="dark" />
          {saga && (
            <div className={`result tone-${sagaTone(saga.status)}`}>
              <b>{SAGA_LABEL[saga.status]}</b>
              <span>
                {saga.errorCode ? ERROR_LABEL[saga.errorCode] ?? saga.errorCode : `Cobro estimado ${money(saga.amount)}`}
              </span>
              <code title="correlation_id (rastreable en CloudWatch)">{saga.correlationId}</code>
            </div>
          )}
        </div>

        <div className="reserve-side">
          <form className="form" onSubmit={submit}>
            <label>
              Flota
              <select value={fleetId} onChange={(e) => setFleetId(e.target.value)}>
                {(fleets.data?.fleets ?? []).map((f) => (
                  <option key={f.fleetId} value={f.fleetId}>
                    {f.fleetName} — {money(f.balance, f.currency)}
                  </option>
                ))}
              </select>
            </label>
            <div className="row">
              <label>
                Estación
                <select value={station?.stationId ?? ""} onChange={(e) => { setStationId(e.target.value); setConnectorId(""); }}>
                  {stations.map((s) => (
                    <option key={s.stationId} value={s.stationId}>
                      {s.name} ({s.city})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Conector
                <select value={connector?.connectorId ?? ""} onChange={(e) => setConnectorId(e.target.value)} disabled={!available.length}>
                  {available.length === 0 && <option>Sin conectores libres</option>}
                  {available.map((c) => (
                    <option key={c.connectorId} value={c.connectorId}>
                      {c.connectorId.toUpperCase()} · {c.connectorType} {c.powerKw} kW
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Energía estimada <b>{kwh} kWh</b>
              <input type="range" min={5} max={80} step={5} value={kwh} onChange={(e) => setKwh(Number(e.target.value))} />
            </label>
            <div className="quote">
              <span>
                {quote ? `${money(quote.pricePerKwh)} / kWh` : "—"}
                {quote?.surgeApplied && <span className="tag warn">tarifa pico ×{quote.surgeMultiplier}</span>}
              </span>
              <strong>{money(quote?.total)}</strong>
            </div>
            {fleet && quote && fleet.balance < quote.total && (
              <p className="hint warn">El saldo no alcanza: la SAGA fallará en el paso 2 y liberará el conector.</p>
            )}
            <button className="btn big" disabled={busy || !connector}>
              {busy ? "Procesando SAGA…" : "Reservar y activar carga"}
            </button>
            {error && <p className="hint bad">{error}</p>}
          </form>
          <SagaSteps steps={saga?.steps ?? []} running={busy} />
        </div>
      </div>
    </section>
  );
}
