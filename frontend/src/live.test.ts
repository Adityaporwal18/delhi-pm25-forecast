import { describe, expect, it } from "vitest";
import type { LivePoint } from "./api";
import { type StationState, ageLabel, hoursSince, nowText, pointsAt, stationPath, statusCounts } from "./live";

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

describe("the forecast's age, in words", () => {
  it.each([
    [0, "just now"],
    [1 / 60, "1 minute ago"],
    [25 / 60, "25 minutes ago"],
    [1, "1 hour ago"],
    [1.4, "1 hour ago"],
    [5, "5 hours ago"],
    [24, "1 day ago"],
    [50, "2 days ago"],
  ])("%s hours old reads as %s", (hours, words) => {
    expect(ageLabel(hours)).toBe(words);
  });
});

describe("why a station has no reading now", () => {
  const reporting: StationState = { slug: "a", status: "reporting", last_value: 170, last_value_utc: "2026-11-22T16:30:00Z", last_reading_utc: "2026-11-22T16:30:00Z" };
  const delayed: StationState = { slug: "b", status: "delayed", last_value: 182, last_value_utc: "2026-11-22T16:15:00Z", last_reading_utc: "2026-11-22T16:15:00Z" };
  const dark: StationState = { slug: "c", status: "analyser_dark", last_value: 300, last_value_utc: "2026-11-22T12:30:00Z", last_reading_utc: "2026-11-22T16:15:00Z" };

  it("counts the stations by status", () => {
    expect(statusCounts([reporting, reporting, delayed, dark])).toBe("2 reporting · 1 delayed · 1 PM2.5 analyser not reporting");
  });

  it("explains the missing reading in words", () => {
    expect([nowText(reporting, 170), nowText(delayed, null), nowText(dark, null)]).toEqual([
      "now: 170",
      "now: not received yet (the feed is running late; latest PM2.5 182 at Sun 22 Nov 2026, 21:45)",
      "now: the PM2.5 analyser has not reported since Sun 22 Nov 2026, 18:00, though the station's other pollutants have",
    ]);
  });

  it("marks stations without a reading now for the map", () => {
    const points = pointsAt(ROWS, 48, [delayed]);
    expect([points.get("b")?.quiet, points.get("a")?.quiet]).toEqual([true, false]);
  });
});
