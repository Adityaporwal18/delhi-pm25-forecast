import { describe, expect, it } from "vitest";
import { STEP_MS, mapHours, nextHour, playFrom } from "./playback";

const HOURS = [6, 12, 18, 24, 30, 36, 42, 48];

describe("playing the map through the forecast hours", () => {
  it("offers only forecast hours, never horizon 0, which is a measurement", () => {
    // Given: the horizons the API lists, starting with 0 (the value measured now)
    // When / Then
    expect(mapHours([0, ...HOURS])).toEqual(HOURS);
  });

  it("steps one forecast hour at a time and stops at the last one", () => {
    // Given: the map at +6 h, then at +48 h
    // When / Then: +12 h comes next; nothing comes after +48 h, so playback stops there
    expect([nextHour(HOURS, 6), nextHour(HOURS, 48)]).toEqual([12, null]);
  });

  it("restarts from the first hour when Play is pressed at the end, and otherwise carries on", () => {
    // Given: the map at +48 h (the default), then at +18 h
    // When / Then
    expect([playFrom(HOURS, 48), playFrom(HOURS, 18)]).toEqual([6, 18]);
  });

  it("shows each forecast hour for one second, so a full sweep takes 7 seconds", () => {
    // Given: eight forecast hours; When: played from the first; Then: seven one-second steps
    expect((HOURS.length - 1) * STEP_MS).toBe(7000);
  });
});
