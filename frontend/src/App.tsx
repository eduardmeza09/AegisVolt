import { useState } from "react";
import { Q } from "./api";
import { Flags } from "./components/Flags";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Hero } from "./components/Hero";
import { History } from "./components/History";
import { Reserve } from "./components/Reserve";
import { Showroom } from "./components/Showroom";
import { Stations } from "./components/Stations";
import { usePoll } from "./hooks";
import type { ChargingSession, Environment, Saga, Station } from "./types";

interface Overview {
  environment: Environment;
  stations: Station[];
  chargingSessions: ChargingSession[];
}

export default function App() {
  const overview = usePoll<Overview>(Q.overview, 3000);
  const recent = usePoll<{ sagas: Saga[] }>(Q.sagas, 6000, { s: null, l: 100 });
  const [pick, setPick] = useState<{ stationId: string; connectorId: string } | null>(null);
  const [version, setVersion] = useState(0);
  const [focus, setFocus] = useState<string | null>(null);

  const env = overview.data?.environment ?? null;
  const stations = overview.data?.stations ?? [];
  const sessions = overview.data?.chargingSessions ?? [];
  const online = !!overview.data && !overview.error;

  return (
    <>
      <div className="backdrop" aria-hidden />
      <Header env={env} online={online} />
      <main>
        <Hero env={env} online={online} updatedAt={overview.updatedAt} />
        <Showroom stations={stations} sessions={sessions} sagas={recent.data?.sagas ?? []} />
        <Stations
          stations={stations}
          sessions={sessions}
          updatedAt={overview.updatedAt}
          error={overview.error}
          onPick={(stationId, c) => {
            setPick({ stationId, connectorId: c.connectorId });
            document.getElementById("reservar")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
        <Reserve
          stations={stations}
          pick={pick}
          onDone={() => {
            overview.refresh();
            recent.refresh();
            setVersion((v) => v + 1);
          }}
        />
        <Flags />
        <History version={version} focus={focus} />
      </main>
      <Footer
        env={env}
        onFind={(id) => {
          setFocus(id);
          document.getElementById("historial")?.scrollIntoView({ behavior: "smooth" });
        }}
      />
    </>
  );
}
