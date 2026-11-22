import { Logo } from "../art/icons";
import type { Environment } from "../types";

const LINKS = [
  ["inicio", "Inicio"],
  ["estaciones", "Estaciones"],
  ["reservar", "Reservar"],
  ["flags", "Flags"],
  ["historial", "Historial"],
] as const;

export function Header({ env, online }: { env: Environment | null; online: boolean }) {
  return (
    <header className="header">
      <a className="brand" href="#inicio" aria-label="AegisVolt inicio">
        <Logo />
        <span>AEGISVOLT</span>
      </a>
      <nav className="nav">
        {LINKS.map(([id, label], i) => (
          <a key={id} href={`#${id}`} className={i === 0 ? "active" : undefined}>
            {i === 0 && <span className="nav-arrow">➤</span>}
            {label}
          </a>
        ))}
      </nav>
      <div className={`env-pill env-${env?.name ?? "na"}`} title={online ? "API conectada" : "Sin conexión con la API"}>
        <span className={`led ${online ? "on" : "off"}`} />
        {env ? env.name.toUpperCase() : "…"}
      </div>
    </header>
  );
}
