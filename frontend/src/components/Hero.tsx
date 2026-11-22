import { Car } from "../art/Car";
import { Charger } from "../art/Charger";
import type { Environment } from "../types";

export function Hero({ env, online, updatedAt }: { env: Environment | null; online: boolean; updatedAt: number | null }) {
  return (
    <section className="hero" id="inicio">
      <div className="mega" aria-hidden>
        ELECTRIC
      </div>
      <div className="hero-art">
        <Charger className="hero-charger" />
        <Car variant="dark" className="hero-car" />
        <div className="floor" />
      </div>
      <div className="hero-foot">
        <p>
          Reserva bahías de carga, retiene saldo y activa sesiones de energía para tu flota eléctrica. Cada operación
          es una transacción distribuida que se compensa sola si algo falla en el camino.
        </p>
        <div className="chips">
          <span className="chip">
            <span className={`led ${online ? "on" : "off"}`} /> {online ? "API en línea" : "API sin conexión"}
          </span>
          <span className="chip">Ambiente · {env?.name ?? "…"}</span>
          <span className="chip">Versión · {env?.version ?? "…"}</span>
          {updatedAt && <span className="chip muted">sync {new Date(updatedAt).toLocaleTimeString("es-CO")}</span>}
        </div>
      </div>
    </section>
  );
}
