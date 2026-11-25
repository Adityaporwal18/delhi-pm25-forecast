import { useEffect, useMemo, useState } from "react";
import { type Accuracy, type Live, type Meta, fetchLive } from "./api";
import { AccuracyPanel } from "./AccuracyPanel";
import { chartRows } from "./chart";
import { StationSelect, defaultStation } from "./controls";
import { Focal, ug } from "./Focal";
import { ForecastChart } from "./ForecastChart";
import { Legend } from "./Legend";
import { STALE_AFTER_HOURS, ageLabel, hoursSince, nowText, pointsAt, stationPath, statusCounts } from "./live";
import { mapHours } from "./playback";
import { StationMap } from "./StationMap";
import { TimeBar, usePlayback } from "./TimeBar";
import { addHours, delhiLabel } from "./time";
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
  const hours = useMemo(() => mapHours(meta.horizons_h), [meta.horizons_h]);
  const [horizon, setHorizon] = useState(48);
  const playback = usePlayback(hours, horizon, setHorizon, true, active);
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
  const marker = points.get(selected);
  return (
    <main className="main">
      <section className="status-strip" aria-label="About this forecast">
        <p className="strip-line">
          <span className="tag">Live</span>
          From <strong>{delhiLabel(live.issued_utc)}</strong> Delhi time, with readings from{" "}
          <strong>
            {live.stations_reporting} of {live.stations} stations
          </strong>
          <span className="sep">·</span>
          last updated {delhiLabel(live.generated_at_utc)} ({ageLabel(age)}); a new forecast about every 3 hours
          {live.station_status.length > 0 && (
            <>
              <span className="sep">·</span>
              {statusCounts(live.station_status)} (dashed outline on the map: no current PM2.5 reading)
            </>
          )}
        </p>
        {age > STALE_AFTER_HOURS && (
          <p className="warning" role="status">
            This forecast is more than {STALE_AFTER_HOURS} hours old: the latest refreshes did not publish (missing or
            doubtful data, or a delayed schedule), so the last good forecast is shown.
          </p>
        )}
      </section>
      <section className="panel map-panel" aria-label="Map of monitoring stations">
        <StationMap stations={meta.stations} points={points} selected={selected} onSelect={setSelected} active={active} />
        <Legend categories={meta.categories} />
        <TimeBar
          hours={hours}
          hour={horizon}
          when={delhiLabel(addHours(live.issued_utc, horizon))}
          playing={playback.playing}
          onToggle={playback.toggle}
          onChoose={playback.choose}
        />
      </section>
      <div className="station-col">
        <section className="panel controls single" aria-label="Station">
          <StationSelect stations={meta.stations} value={selected} onChange={setSelected} />
        </section>
        <section className="panel primary" aria-labelledby="live-chart-title">
          <h2 id="live-chart-title" className="station-name">
            {station?.name ?? selected}
          </h2>
          {ahead !== undefined && ahead.p50 !== null ? (
            <Focal
              value={ahead.p50}
              when={`expected ${delhiLabel(ahead.valid_utc)}`}
              detail={`80% band ${ug(ahead.p10)}–${ug(ahead.p90)} · ${nowText(state, now?.measured ?? null)}`}
              category={marker ?? null}
            />
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
          {path.length > 0 && <ForecastChart rows={chartRows(path)} categories={meta.categories} hour={horizon} />}
          <p className="caption">
            Line: median forecast · shaded: 80% band (8 in 10 measured values should fall inside) · dot at “now”: the
            latest reading, when the station has one · dashed line: the hour the map shows.
          </p>
        </section>
      </div>
      <aside className="context-col">
        <AccuracyPanel accuracy={accuracy} framing="expected" />
      </aside>
    </main>
  );
}
