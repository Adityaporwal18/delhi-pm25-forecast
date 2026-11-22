import { describe, expect, it } from "vitest";
import type { LivePoint } from "./api";
import { hoursSince, pointsAt, stationPath } from "./live";

// Given: two stations; "b" has the value measured now (horizon 0) and a 48-hour forecast
const ROWS: LivePoint[] = [
  { slug: "b", horizon_h: 48, valid_utc: "2026-11-24T16:30:00Z", p10: 80, p50: 150, p90: 240, measured: null, category: "Very Poor", colour: "#ff0000" },
  { slug: "b", horizon_h: 0, valid_utc: "2026-11-22T16:30:00Z", p10: null, p50: null, p90: null, measured: 170, category: null, colour: null },
  { slug: "a", horizon_h: 48, valid_utc: "2026-11-24T16:30:00Z", p10: 30, p50: 60, p90: 95, measured: null, category: "Satisfactory", colour: "#92d050" },
];

describe("live forecast helpers", () => {
  it("give each station's forecast for the chosen horizon, for the map", () => {
    const points = pointsAt(ROWS, 48);
    expect([[...points.keys()].sort(), points.get("b")?.p50, points.get("a")?.colour]).toEqual([["a", "b"], 150, "#92d050"]);
  });

  it("give one station's path from now to the last horizon, for the chart", () => {
    expect(stationPath(ROWS, "b").map((point) => [point.horizon_h, point.measured, point.p50])).toEqual([
      [0, 170, null],
      [48, null, 150],
    ]);
  });

  it("give the forecast's age in hours", () => {
    expect(hoursSince("2026-11-22T17:15:00Z", Date.parse("2026-11-22T20:15:00Z"))).toBe(3);
  });
});
