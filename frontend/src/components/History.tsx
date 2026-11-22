import { useEffect, useState } from "react";
import { gql, Q } from "../api";
import { Copy } from "../art/icons";
import { usePoll } from "../hooks";
import { ERROR_LABEL, money, SAGA_LABEL, sagaTone, shortId, timeAgo } from "../lib";
import type { Saga, SagaStatus } from "../types";
import { SagaSteps } from "./SagaSteps";

const FILTERS: [string, SagaStatus | null][] = [
  ["Todas", null],
  ["Cargando", "COMPLETED"],
  ["Finalizadas", "FINISHED"],
  ["Compensadas", "COMPENSATED"],
  ["Fallidas", "FAILED"],
  ["Compensación fallida", "COMPENSATION_FAILED"],
];

export function History({ version, focus }: { version: number; focus: string | null }) {
  const [filter, setFilter] = useState<SagaStatus | null>(null);
  const { data, error, refresh } = usePoll<{ sagas: Saga[] }>(Q.sagas, 4000, { s: filter, l: 40 });
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    refresh();
  }, [version, refresh]);

  const [focused, setFocused] = useState<Saga | null>(null);
  useEffect(() => {
    if (!focus) return;
    setFilter(null);
    setOpen(focus);
    gql<{ saga: Saga | null }>(Q.saga, { id: focus })
      .then((d) => {
        setFocused(d.saga);
        setMsg(d.saga ? null : `No existe una saga con id ${focus} en este ambiente.`);
      })
      .catch((e) => setMsg((e as Error).message));
  }, [focus]);

  const listed = data?.sagas ?? [];
  const sagas = focused && !listed.some((s) => s.sagaId === focused.sagaId) ? [focused, ...listed] : listed;
  const all = listed;
  const counts = {
    ok: all.filter((s) => sagaTone(s.status) === "ok").length,
    warn: all.filter((s) => s.status === "COMPENSATED").length,
    bad: all.filter((s) => sagaTone(s.status) === "bad").length,
  };

  async function act(kind: "stop" | "retry", sagaId: string) {
    setBusy(sagaId);
    setMsg(null);
    try {
      await gql(kind === "stop" ? Q.stop : Q.retry, { id: sagaId });
      setMsg(kind === "retry" ? "Compensación re-ejecutada: los pasos *_REPLAY muestran que no se movió dinero dos veces." : "Carga detenida y conector liberado.");
      refresh();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="section" id="historial">
      <div className="history-intro">
        <h2 className="title">
          Historial de
          <br />
          <em>transacciones</em>
        </h2>
        <div>
          <p>
            Cada fila es una SAGA persistida por el orquestador. Si un paso falla, las compensaciones se ejecutan en
            orden inverso: primero el reembolso, después la liberación del conector.
          </p>
          <p>
            El <code>correlation_id</code> permite rastrear la transacción completa en CloudWatch, en los log groups
            de los cuatro servicios.
          </p>
          <dl className="mini-stats">
            <div className="tone-ok"><dt>{counts.ok}</dt><dd>exitosas</dd></div>
            <div className="tone-warn"><dt>{counts.warn}</dt><dd>compensadas</dd></div>
            <div className="tone-bad"><dt>{counts.bad}</dt><dd>fallidas</dd></div>
          </dl>
        </div>
      </div>

      <div className="tabs" role="tablist">
        {FILTERS.map(([label, value]) => (
          <button key={label} type="button" role="tab" aria-selected={filter === value}
            className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>
            {label}
          </button>
        ))}
      </div>
      {error && <p className="hint bad">{error}</p>}
      {msg && <p className="hint">{msg}</p>}

      <div className="table">
        {sagas.length === 0 && <p className="muted empty">Sin transacciones para este filtro.</p>}
        {sagas.map((s) => {
          const isOpen = open === s.sagaId;
          return (
            <div key={s.sagaId} className={`trow ${isOpen ? "open" : ""}`} id={`saga-${s.sagaId}`}>
              <button type="button" className="trow-head" onClick={() => setOpen(isOpen ? null : s.sagaId)}>
                <span className={`badge tone-${sagaTone(s.status)}`}>{SAGA_LABEL[s.status]}</span>
                <span className="mono">{shortId(s.sagaId)}</span>
                <span>{s.fleetId}</span>
                <span>
                  {s.stationId} / {s.connectorId?.toUpperCase()}
                </span>
                <span>{money(s.amount)}{s.surgeApplied ? " ⚡" : ""}</span>
                <span className="muted">{s.errorCode ? ERROR_LABEL[s.errorCode] ?? s.errorCode : "—"}</span>
                <span className="muted">{timeAgo(s.createdAt)}</span>
              </button>
              {isOpen && (
                <div className="trow-body">
                  <SagaSteps steps={s.steps} />
                  <div className="trow-actions">
                    <button type="button" className="btn ghost" onClick={() => navigator.clipboard?.writeText(s.correlationId)}>
                      <Copy /> correlation_id
                    </button>
                    <code>{s.correlationId}</code>
                    {s.status === "COMPLETED" && (
                      <button type="button" className="btn" disabled={busy === s.sagaId} onClick={() => act("stop", s.sagaId)}>
                        Detener carga
                      </button>
                    )}
                    {(s.status === "COMPENSATED" || s.status === "COMPENSATION_FAILED") && (
                      <button type="button" className="btn" disabled={busy === s.sagaId} onClick={() => act("retry", s.sagaId)}>
                        Reintentar compensación
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
