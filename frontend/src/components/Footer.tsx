import { useState } from "react";
import { Logo, Search } from "../art/icons";
import type { Environment } from "../types";

export function Footer({ env, onFind }: { env: Environment | null; onFind: (id: string) => void }) {
  const [q, setQ] = useState("");
  return (
    <footer className="footer">
      <div className="footer-grid">
        <Logo size={40} />
        <div>
          <h4>Secciones</h4>
          <a href="#inicio">Inicio</a>
          <a href="#estaciones">Estaciones</a>
          <a href="#reservar">Reservar</a>
          <a href="#flags">Feature flags</a>
          <a href="#historial">Historial</a>
        </div>
        <div>
          <h4>Ambiente</h4>
          <p>Ambiente: <b>{env?.name ?? "…"}</b></p>
          <p>Versión: <b>{env?.version ?? "…"}</b></p>
          <p>Pod: <b>{env?.podTemplateHash ?? "…"}</b></p>
        </div>
        <div>
          <h4>Buscar SAGA</h4>
          <form className="search" onSubmit={(e) => { e.preventDefault(); if (q.trim()) onFind(q.trim()); }}>
            <input placeholder="correlation_id" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn" aria-label="Buscar"><Search /></button>
          </form>
        </div>
      </div>
      <div className="footer-bottom">
        <span>© 2026 <em>AegisVolt</em> · Gestión de carga para flotas eléctricas</span>
        <span className="links">
          <a href="https://github.com/eduardmeza09/AegisVolt" target="_blank" rel="noreferrer">Repositorio</a>
          <a href="https://github.com/eduardmeza09/AegisVolt/blob/dev/docs/arquitectura.md" target="_blank" rel="noreferrer">Arquitectura</a>
        </span>
      </div>
      <div className="mega bottom" aria-hidden>ELECTRIC</div>
    </footer>
  );
}
