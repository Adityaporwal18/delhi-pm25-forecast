import { useMemo, useState } from "react";
import { type Accuracy, type Meta, fetchForecast, fetchMap } from "./api";
import { AccuracyPanel } from "./AccuracyPanel";
import { chartRows } from "./chart";
import { HorizonButtons, StationSelect, defaultStation } from "./controls";
import { Focal, ug } from "./Focal";
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
      <section className="status-strip" aria-label="About this replay">
        <p className="strip-line">
          <span className="tag">Replay of 2025</span>
          What the evaluation model forecast at <strong>{delhiLabel(issued)}</strong> (Delhi time), next to what was
          measured later.
        </p>
      </section>
      <section className="panel map-panel" aria-label="Map of monitoring stations">
        <StationMap stations={meta.stations} points={bySlug} selected={selected} onSelect={setSelected} active={active} />
        <Legend categories={meta.categories} />
        {points.state !== "ready" && <Status load={points} what="the map" retry={retryPoints} />}
      </section>
      <div className="station-col">
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
        <section className="panel primary" aria-labelledby="chart-title">
          <h2 id="chart-title" className="station-name">
            {station?.name ?? selected}
          </h2>
          {ahead !== undefined && ahead.p50 !== null && (
            <Focal
              value={ahead.p50}
              when={`forecast for ${delhiLabel(ahead.valid_utc)}`}
              detail={`80% band ${ug(ahead.p10)}–${ug(ahead.p90)} · measured then: ${ahead.measured === null ? "no reading" : ug(ahead.measured)}`}
              category={bySlug.get(selected) ?? null}
            />
          )}
          {forecast.state === "ready" ? (
            <ForecastChart rows={chartRows(forecast.data)} categories={meta.categories} />
          ) : (
            <Status load={forecast} what="the forecast" retry={retryForecast} />
          )}
          <p className="caption">Line: median forecast · shaded: 80% band · dots: what was measured.</p>
        </section>
      </div>
      <aside className="context-col">
        <AccuracyPanel accuracy={accuracy} framing="measured" />
      </aside>
    </main>
  );
}
