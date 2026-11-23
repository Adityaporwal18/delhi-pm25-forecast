import type { ForecastPoint, LivePoint, MapPoint } from "./api";

/** After this many hours the page warns that the live forecast is older than the 6-hour schedule allows. */
export const STALE_AFTER_HOURS = 12;

/** Each station's forecast `horizon` hours ahead, keyed by station, as the map reads it. */
export function pointsAt(rows: readonly LivePoint[], horizon: number): Map<string, MapPoint> {
  return new Map(
    rows
      .filter((row) => row.horizon_h === horizon)
      .map((row): [string, MapPoint] => [
        row.slug,
        { slug: row.slug, p10: row.p10, p50: row.p50, p90: row.p90, measured: row.measured, category: row.category, colour: row.colour },
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
