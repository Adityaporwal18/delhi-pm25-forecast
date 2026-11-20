import { useEffect, useMemo, useState } from "react";
import { type Meta, fetchForecast, fetchMap, fetchMeta } from "./api";
import { chartRows } from "./chart";
import { ForecastChart } from "./ForecastChart";
import { Legend } from "./Legend";
import { StationMap } from "./StationMap";
import { delhiDate, delhiHour, delhiLabel, findIssueTime } from "./time";

type Load<T> = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

/** Runs `load` whenever `key` changes (or on retry); a newer request cancels the older one. */
function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, key: string): [Load<T>, () => void] {
  const [result, setResult] = useState<Load<T>>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setResult({ state: "loading" });
    load(controller.signal).then(
      (data) => setResult({ state: "ready", data }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setResult({ state: "error", message: error instanceof Error ? error.message : String(error) });
        }
      },
    );
    return () => controller.abort();
    // `load` is a new closure on every render; `key` names what it loads.
  }, [key, attempt]); // eslint-disable-line react-hooks/exhaustive-deps
  return [result, () => setAttempt((count) => count + 1)];
}

function Status({ load, what, retry }: { load: Load<unknown>; what: string; retry: () => void }) {
  if (load.state === "error") {
    return (
      <p className="status error" role="alert">
        Could not load {what}: {load.message}{" "}
        <button type="button" className="button" onClick={retry}>
          Retry
        </button>
      </p>
    );
  }
  return (
    <p className="status" aria-live="polite">
      Loading {what}…
    </p>
  );
}

export function App() {
  const [meta, retry] = useLoad(fetchMeta, "meta");
  if (meta.state !== "ready") {
    return (
      <div className="page">
        <Status load={meta} what="the stations" retry={retry} />
      </div>
    );
  }
  return <Dashboard meta={meta.data} />;
}

function Dashboard({ meta }: { meta: Meta }) {
  const times = meta.issue_times_utc;
  const [issued, setIssued] = useState(findIssueTime(times, "2025-11-01", 8) ?? times[0] ?? "");
  const [horizon, setHorizon] = useState(48);
  const [selected, setSelected] = useState(
    meta.stations.find((station) => station.slug === "anand_vihar_dpcc")?.slug ?? meta.stations[0]?.slug ?? "",
  );
  const [points, retryPoints] = useLoad((signal) => fetchMap(issued, horizon, signal), `${issued}|${horizon}`);
  const [forecast, retryForecast] = useLoad((signal) => fetchForecast(selected, issued, signal), `${selected}|${issued}`);
  const bySlug = useMemo(() => new Map((points.state === "ready" ? points.data : []).map((point) => [point.slug, point])), [points]);
  const hours = useMemo(() => [...new Set(times.map(delhiHour))].sort((a, b) => a - b), [times]);
  const stations = useMemo(() => [...meta.stations].sort((a, b) => a.name.localeCompare(b.name)), [meta.stations]);
  const station = meta.stations.find((candidate) => candidate.slug === selected);
  const ahead = forecast.state === "ready" ? forecast.data.find((point) => point.horizon_h === horizon) : undefined;

  function choose(date: string, hour: number) {
    const time = findIssueTime(times, date, hour);
    if (time !== undefined) {
      setIssued(time);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1 className="title">
            Delhi PM2.5 forecast <span className="title-soft">— 48 hours ahead</span>
          </h1>
          <p className="caption">
            {meta.stations.length} CPCB monitoring stations · forecasts made at {delhiLabel(issued)} (Delhi time)
          </p>
        </div>
        <span className="notice">Replay of 2025, not a live forecast</span>
      </header>
      <main className="main">
        <section className="panel map-panel" aria-label="Map of monitoring stations">
          <StationMap stations={meta.stations} points={bySlug} selected={selected} onSelect={setSelected} />
          {points.state !== "ready" && <Status load={points} what="the map" retry={retryPoints} />}
        </section>
        <aside className="side">
          <section className="panel controls" aria-label="Forecast time and station">
            <label className="field">
              <span>Forecast made on</span>
              <input
                type="date"
                value={delhiDate(issued)}
                min={delhiDate(times[0] ?? issued)}
                max={delhiDate(times[times.length - 1] ?? issued)}
                onChange={(event) => choose(event.target.value, delhiHour(issued))}
              />
            </label>
            <label className="field">
              <span>at (Delhi time)</span>
              <select value={delhiHour(issued)} onChange={(event) => choose(delhiDate(issued), Number(event.target.value))}>
                {hours.map((hour) => (
                  <option key={hour} value={hour}>{`${String(hour).padStart(2, "0")}:00`}</option>
                ))}
              </select>
            </label>
            <div className="field">
              <span id="horizon-label">Map shows hours ahead</span>
              <div className="segmented" role="group" aria-labelledby="horizon-label">
                {meta.horizons_h
                  .filter((hoursAhead) => hoursAhead > 0)
                  .map((hoursAhead) => (
                    <button key={hoursAhead} type="button" aria-pressed={hoursAhead === horizon} onClick={() => setHorizon(hoursAhead)}>
                      {hoursAhead}
                    </button>
                  ))}
              </div>
            </div>
            <label className="field">
              <span>Station</span>
              <select value={selected} onChange={(event) => setSelected(event.target.value)}>
                {stations.map((option) => (
                  <option key={option.slug} value={option.slug}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
          </section>
          <section className="panel chart-card" aria-labelledby="chart-title">
            <h2 id="chart-title" className="heading">
              {station?.name ?? selected}
            </h2>
            {ahead !== undefined && ahead.p50 !== null && (
              <p className="summary">
                <span className="value">{ahead.p50}</span> µg/m³ forecast for {delhiLabel(ahead.valid_utc)}
                <span className="caption block">
                  80% band {ahead.p10}–{ahead.p90} · measured then: {ahead.measured ?? "no reading"}
                </span>
              </p>
            )}
            {forecast.state === "ready" ? (
              <ForecastChart rows={chartRows(forecast.data)} categories={meta.categories} />
            ) : (
              <Status load={forecast} what="the forecast" retry={retryForecast} />
            )}
            <p className="caption">Line: median forecast · shaded: 80% band · dots: what was measured.</p>
          </section>
          <Legend categories={meta.categories} />
        </aside>
      </main>
      <footer className="footer">
        <p>{meta.note}</p>
        <p>{meta.credits}</p>
      </footer>
    </div>
  );
}
