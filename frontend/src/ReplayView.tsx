import { useMemo, useState } from "react";
import { type Accuracy, type Meta, fetchForecast, fetchMap } from "./api";
import { AccuracyPanel } from "./AccuracyPanel";
import { chartRows } from "./chart";
import { HorizonButtons, StationSelect, defaultStation } from "./controls";
import { ForecastChart } from "./ForecastChart";
import { Legend } from "./Legend";
import { StationMap } from "./StationMap";
import { delhiDate, delhiHour, delhiLabel, findIssueTime } from "./time";
import { Status, useLoad } from "./useLoad";

/** The 2025 replay: what the evaluation model forecast at a chosen moment, next to what was measured. */
export function ReplayView({ meta, accuracy, active }: { meta: Meta; accuracy: Accuracy; active: boolean }) {
  const times = meta.issue_times_utc;
  const [issued, setIssued] = useState(findIssueTime(times, "2025-11-01", 8) ?? times[0] ?? "");
  const [horizon, setHorizon] = useState(48);
  const [selected, setSelected] = useState(defaultStation(meta));
  const [points, retryPoints] = useLoad((signal) => fetchMap(issued, horizon, signal), `${issued}|${horizon}`);
  const [forecast, retryForecast] = useLoad((signal) => fetchForecast(selected, issued, signal), `${selected}|${issued}`);
  const bySlug = useMemo(() => new Map((points.state === "ready" ? points.data : []).map((point) => [point.slug, point])), [points]);
  const hours = useMemo(() => [...new Set(times.map(delhiHour))].sort((a, b) => a - b), [times]);
  const station = meta.stations.find((candidate) => candidate.slug === selected);
  const ahead = forecast.state === "ready" ? forecast.data.find((point) => point.horizon_h === horizon) : undefined;

  function choose(date: string, hour: number) {
    const time = findIssueTime(times, date, hour);
    if (time !== undefined) {
      setIssued(time);
    }
  }

  return (
    <main className="main">
      <section className="panel map-panel" aria-label="Map of monitoring stations">
        <StationMap stations={meta.stations} points={bySlug} selected={selected} onSelect={setSelected} active={active} />
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
          <HorizonButtons horizons={meta.horizons_h} value={horizon} onChange={setHorizon} />
          <StationSelect stations={meta.stations} value={selected} onChange={setSelected} />
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
        <AccuracyPanel accuracy={accuracy} framing="measured" />
        <Legend categories={meta.categories} />
      </aside>
    </main>
  );
}
