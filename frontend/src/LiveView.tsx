import { useEffect, useMemo, useState } from "react";
import { type Accuracy, type Live, type Meta, fetchLive } from "./api";
import { AccuracyPanel } from "./AccuracyPanel";
import { chartRows } from "./chart";
import { HorizonButtons, StationSelect, defaultStation } from "./controls";
import { ForecastChart } from "./ForecastChart";
import { Legend } from "./Legend";
import { STALE_AFTER_HOURS, ageLabel, hoursSince, nowText, pointsAt, stationPath, statusCounts } from "./live";
import { StationMap } from "./StationMap";
import { delhiLabel } from "./time";
import { Status, useLoad } from "./useLoad";

interface Props {
  meta: Meta;
  accuracy: Accuracy;
  /** False while the Accuracy tab is shown: the view stays mounted, hidden, keeping its data. */
  active: boolean;
}

/** The next 48 hours, from the latest live forecast (refreshed about every 3 hours). */
export function LiveView({ meta, accuracy, active }: Props) {
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
  return <LiveDashboard meta={meta} accuracy={accuracy} active={active} live={live.data} />;
}

function LiveDashboard({ meta, accuracy, active, live }: Props & { live: Live }) {
  const [horizon, setHorizon] = useState(48);
  const [selected, setSelected] = useState(defaultStation(meta));
  const points = useMemo(() => pointsAt(live.rows, horizon, live.station_status), [live.rows, horizon, live.station_status]);
  const state = live.station_status.find((candidate) => candidate.slug === selected);
  const path = useMemo(() => stationPath(live.rows, selected), [live.rows, selected]);
  const ahead = path.find((point) => point.horizon_h === horizon);
  const now = path.find((point) => point.horizon_h === 0);
  const [nowMs, setNowMs] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const age = hoursSince(live.generated_at_utc, nowMs);
  const station = meta.stations.find((candidate) => candidate.slug === selected);
  return (
    <main className="main">
      <section className="panel map-panel" aria-label="Map of monitoring stations">
        <StationMap stations={meta.stations} points={points} selected={selected} onSelect={setSelected} active={active} />
      </section>
      <aside className="side">
        <section className="panel" aria-label="About this forecast">
          <p className="lead">
            Forecast from <strong>{delhiLabel(live.issued_utc)}</strong> (Delhi time), with readings from{" "}
            {live.stations_reporting} of {live.stations} stations.
          </p>
          <p className="caption">
            Last updated {delhiLabel(live.generated_at_utc)} ({ageLabel(age)}). A new forecast is made about every 3 hours.
          </p>
          {live.station_status.length > 0 && (
            <p className="caption">
              {statusCounts(live.station_status)}. A dashed outline on the map marks a station with no current PM2.5
              reading.
            </p>
          )}
          {age > STALE_AFTER_HOURS && (
            <p className="warning" role="status">
              This forecast is more than {STALE_AFTER_HOURS} hours old: the latest refreshes did not publish (missing or
              doubtful data, or a delayed schedule), so the last good forecast is shown.
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
                80% band {ahead.p10}–{ahead.p90} · {nowText(state, now?.measured ?? null)}
              </span>
            </p>
          ) : (
            <p className="caption">No live forecast for this station right now.</p>
          )}
          {state !== undefined && state.status !== "reporting" && (
            <p className="caption">Made without this station's current reading: from the city median and its older readings.</p>
          )}
          {state?.status === "analyser_dark" && live.heavy_smog_now && (
            <p className="warning">
              In heavy smog, analysers often stop reporting the highest values (see the README's most important
              limitation), so this station may be worse than its neighbours.
            </p>
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
