import { useMemo, useState } from "react";
import { type Accuracy, type Live, type Meta, fetchLive } from "./api";
import { AccuracyPanel } from "./AccuracyPanel";
import { chartRows } from "./chart";
import { HorizonButtons, StationSelect, defaultStation } from "./controls";
import { ForecastChart } from "./ForecastChart";
import { Legend } from "./Legend";
import { STALE_AFTER_HOURS, hoursSince, pointsAt, stationPath } from "./live";
import { StationMap } from "./StationMap";
import { delhiLabel } from "./time";
import { Status, useLoad } from "./useLoad";

interface Props {
  meta: Meta;
  accuracy: Accuracy;
}

function ageLabel(hours: number): string {
  return hours < 1 ? "less than an hour ago" : `${Math.round(hours)} hours ago`;
}

/** The next 48 hours, from the latest live forecast (refreshed every 6 hours). */
export function LiveView({ meta, accuracy }: Props) {
  const [live, retry] = useLoad(fetchLive, "live");
  if (live.state !== "ready") {
    return (
      <main className="main single">
        <section className="panel">
          <Status load={live} what="the live forecast" retry={retry} />
          <p className="caption">The 2025 replay under “Accuracy” works without it.</p>
        </section>
      </main>
    );
  }
  return <LiveDashboard meta={meta} accuracy={accuracy} live={live.data} />;
}

function LiveDashboard({ meta, accuracy, live }: Props & { live: Live }) {
  const [horizon, setHorizon] = useState(48);
  const [selected, setSelected] = useState(defaultStation(meta));
  const points = useMemo(() => pointsAt(live.rows, horizon), [live.rows, horizon]);
  const path = useMemo(() => stationPath(live.rows, selected), [live.rows, selected]);
  const ahead = path.find((point) => point.horizon_h === horizon);
  const now = path.find((point) => point.horizon_h === 0);
  const age = hoursSince(live.generated_at_utc, Date.now());
  const station = meta.stations.find((candidate) => candidate.slug === selected);
  return (
    <main className="main">
      <section className="panel map-panel" aria-label="Map of monitoring stations">
        <StationMap stations={meta.stations} points={points} selected={selected} onSelect={setSelected} />
      </section>
      <aside className="side">
        <section className="panel" aria-label="About this forecast">
          <p className="lead">
            Forecast from <strong>{delhiLabel(live.issued_utc)}</strong> (Delhi time), with readings from{" "}
            {live.stations_reporting} of {live.stations} stations.
          </p>
          <p className="caption">
            Last updated {delhiLabel(live.generated_at_utc)} ({ageLabel(age)}). A new forecast is made every 6 hours.
          </p>
          {age > STALE_AFTER_HOURS && (
            <p className="warning" role="status">
              This forecast is older than the 6-hour schedule allows: the latest refreshes did not publish (missing or
              doubtful data), so the last good forecast is shown.
            </p>
          )}
        </section>
        <section className="panel controls single" aria-label="Hours ahead and station">
          <HorizonButtons horizons={meta.horizons_h} value={horizon} onChange={setHorizon} />
          <StationSelect stations={meta.stations} value={selected} onChange={setSelected} />
        </section>
        <section className="panel chart-card" aria-labelledby="live-chart-title">
          <h2 id="live-chart-title" className="heading">
            {station?.name ?? selected}
          </h2>
          {ahead !== undefined && ahead.p50 !== null ? (
            <p className="summary">
              <span className="value">{ahead.p50}</span> µg/m³ expected for {delhiLabel(ahead.valid_utc)}
              <span className="caption block">
                80% band {ahead.p10}–{ahead.p90} · now: {now?.measured ?? "no reading yet"}
              </span>
            </p>
          ) : (
            <p className="caption">No live forecast for this station right now.</p>
          )}
          {path.length > 0 && <ForecastChart rows={chartRows(path)} categories={meta.categories} />}
          <p className="caption">
            Line: median forecast · shaded: 80% band (8 in 10 measured values should fall inside) · dot at “now”: the
            latest reading, when the station has one.
          </p>
        </section>
        <AccuracyPanel accuracy={accuracy} framing="expected" />
        <Legend categories={meta.categories} />
      </aside>
    </main>
  );
}
