import type { ForecastPoint } from "./api";

/** One point on a station's 48-hour chart. `band` is the 10th to 90th percentile range. */
export interface ChartRow {
  horizon: number;
  band: [number, number] | null;
  median: number | null;
  measured: number | null;
}

/** API points -> chart rows. The line and the band start at the value measured now (hour 0),
 * where nothing is uncertain, and the band then fans out with the hours ahead. */
function bandOf(point: ForecastPoint): [number, number] | null {
  if (point.horizon_h === 0) {
    return point.measured === null ? null : [point.measured, point.measured];
  }
  return point.p10 !== null && point.p90 !== null ? [point.p10, point.p90] : null;
}

export function chartRows(points: readonly ForecastPoint[]): ChartRow[] {
  return points.map((point) => ({
    horizon: point.horizon_h,
    band: bandOf(point),
    median: point.horizon_h === 0 ? point.measured : point.p50,
    measured: point.measured,
  }));
}

/** A tick at every horizon in the data, so none can go missing (e.g. 42 hours). */
export function axisTicks(rows: readonly ChartRow[]): number[] {
  return [...new Set(rows.map((row) => row.horizon))].sort((a, b) => a - b);
}

/** Short tick labels, so all of them fit side by side even on a phone. */
export function tickLabel(hours: number): string {
  return hours === 0 ? "now" : `+${hours}`;
}
