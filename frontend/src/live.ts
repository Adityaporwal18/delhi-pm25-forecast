import type { ForecastPoint, Live, LivePoint, MapPoint } from "./api";
import { delhiLabel } from "./time";

/** After this many hours the page warns that the live forecast is stale (refreshes run about every 3 hours). */
export const STALE_AFTER_HOURS = 12;

export type StationState = Live["station_status"][number];

/** A map point; `quiet` marks a station with no reading for the forecast hour. */
export type MarkerPoint = MapPoint & { quiet: boolean };

/** Each station's forecast `horizon` hours ahead, keyed by station, as the map reads it. */
export function pointsAt(rows: readonly LivePoint[], horizon: number, states: readonly StationState[] = []): Map<string, MarkerPoint> {
  const quiet = new Set(states.filter((state) => state.status !== "reporting").map((state) => state.slug));
  return new Map(
    rows
      .filter((row) => row.horizon_h === horizon)
      .map((row): [string, MarkerPoint] => [
        row.slug,
        { slug: row.slug, p10: row.p10, p50: row.p50, p90: row.p90, measured: row.measured, category: row.category, colour: row.colour, quiet: quiet.has(row.slug) },
      ]),
  );
}

/** One station's path from now (horizon 0: the value measured now) to the last horizon, as the chart reads it. */
export function stationPath(rows: readonly LivePoint[], slug: string): ForecastPoint[] {
  return rows
    .filter((row) => row.slug === slug)
    .sort((a, b) => a.horizon_h - b.horizon_h)
    .map((row) => ({ horizon_h: row.horizon_h, valid_utc: row.valid_utc, p10: row.p10, p50: row.p50, p90: row.p90, measured: row.measured }));
}

export function hoursSince(isoUtc: string, nowMs: number): number {
  return (nowMs - Date.parse(isoUtc)) / 3_600_000;
}

const RELATIVE = new Intl.RelativeTimeFormat("en", { numeric: "always" });

/** "just now", "1 minute ago", "5 hours ago", "1 day ago": singular and plural handled by Intl. */
export function ageLabel(hours: number): string {
  const minutes = Math.round(hours * 60);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return RELATIVE.format(-minutes, "minute");
  }
  const wholeHours = Math.round(hours);
  return wholeHours < 24 ? RELATIVE.format(-wholeHours, "hour") : RELATIVE.format(-Math.round(hours / 24), "day");
}

const STATUS_WORDS: Record<StationState["status"], string> = {
  reporting: "reporting",
  delayed: "delayed",
  analyser_dark: "PM2.5 analyser not reporting",
  set_aside: "reading set aside",
  silent: "silent",
};

/** "32 reporting · 4 delayed · 1 PM2.5 analyser not reporting" (fixed order, zero counts left out). */
export function statusCounts(states: readonly StationState[]): string {
  return (Object.keys(STATUS_WORDS) as StationState["status"][])
    .map((status) => [status, states.filter((state) => state.status === status).length] as const)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `${count} ${STATUS_WORDS[status]}`)
    .join(" · ");
}

function since(isoUtc: string | null): string {
  return isoUtc === null ? "" : ` since ${delhiLabel(isoUtc)}`;
}

/** What the chart says about the station's value now, including why it is missing. */
export function nowText(state: StationState | undefined, measured: number | null): string {
  if (measured !== null) {
    return `now: ${measured}`;
  }
  if (state === undefined) {
    return "now: no reading yet";
  }
  switch (state.status) {
    case "reporting":
      return "now: no reading yet";
    case "delayed":
      return state.last_value === null || state.last_value_utc === null
        ? "now: not received yet (the feed is running late)"
        : `now: not received yet (the feed is running late; latest PM2.5 ${state.last_value} at ${delhiLabel(state.last_value_utc)})`;
    case "analyser_dark":
      return `now: the PM2.5 analyser has not reported${since(state.last_value_utc)}, though the station's other pollutants have`;
    case "set_aside":
      return "now: the latest reading was set aside (it looked like a glitch or a stuck analyser)";
    case "silent":
      return `now: the station has been silent${since(state.last_reading_utc)}`;
  }
}
