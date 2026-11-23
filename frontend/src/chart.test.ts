import { expect, it } from "vitest";
import type { ForecastPoint } from "./api";
import { axisTicks, chartRows, tickLabel } from "./chart";

it("starts the forecast line and the band at the value measured now", () => {
  // Given: the API's points for "now" and for 6 hours ahead
  const points: ForecastPoint[] = [
    { horizon_h: 0, valid_utc: "2025-11-01T02:30:00Z", p10: null, p50: null, p90: null, measured: 144 },
    { horizon_h: 6, valid_utc: "2025-11-01T08:30:00Z", p10: 66.2, p50: 84.7, p90: 148.3, measured: 219 },
  ];
  // When / Then
  expect(chartRows(points)).toEqual([
    { horizon: 0, band: [144, 144], median: 144, measured: 144 },
    { horizon: 6, band: [66.2, 148.3], median: 84.7, measured: 219 },
  ]);
});

it("puts a tick at every horizon in the data, 42 hours included", () => {
  const rows = chartRows([0, 6, 42, 48].map((horizon_h) => ({ horizon_h, valid_utc: "", p10: 1, p50: 2, p90: 3, measured: null })));
  expect([axisTicks(rows), [0, 42].map(tickLabel)]).toEqual([[0, 6, 42, 48], ["now", "+42"]]);
});
