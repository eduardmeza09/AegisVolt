import { Car } from "../art/Car";
import type { ChargingSession, Saga, Station } from "../types";

interface Props {
  stations: Station[];
  sessions: ChargingSession[];
  sagas: Saga[];
}

export function Showroom({ stations, sessions, sagas }: Props) {
  const connectors = stations.flatMap((s) => s.connectors);
  const available = connectors.filter((c) => c.status === "AVAILABLE").length;
  const compensated = sagas.filter((s) => s.status === "COMPENSATED").length;
  const kw = sessions.reduce((acc, s) => acc + s.powerKwNow, 0);
  const stats = [
    [stations.length, "electrolineras"],
    [`${available}/${connectors.length}`, "conectores libres"],
    [`${kw.toFixed(0)} kW`, "potencia entregada"],
    [compensated, "sagas compensadas"],
  ];
  return (
    <section className="section showroom">
      <h2 className="title right">
        Impulsando un futuro <br />
        <em>más inteligente</em>
      </h2>
      <div className="stage">
        <Car variant="white" className="stage-car left" />
        <Car variant="white" className="stage-car right" />
        <Car variant="white" className="stage-car center" />
      </div>
      <div className="showroom-foot">
        <div>
          <p>
            Los vehículos eléctricos están cambiando la logística de última milla. AegisVolt coordina estaciones,
            billeteras de flota y despacho de energía en tiempo real.
          </p>
          <a className="btn" href="#estaciones">
            Ver estaciones
          </a>
        </div>
        <dl className="stats">
          {stats.map(([value, label]) => (
            <div key={String(label)}>
              <dt>{value}</dt>
              <dd>{label}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
