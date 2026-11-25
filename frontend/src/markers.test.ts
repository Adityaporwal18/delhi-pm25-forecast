import { describe, expect, it } from "vitest";
import { MAX_RADIUS, MIN_RADIUS, RADIUS_AT_250, drawOrder, markerRadius, valueLabels } from "./markers";

describe("map dot sizes", () => {
  it("make the dot's area, not its radius, proportional to the forecast", () => {
    // Given: one forecast four times another; When / Then: twice the radius, so four times the area
    expect(markerRadius(160) / markerRadius(40)).toBeCloseTo(2, 9);
  });

  it("anchor the scale at the Severe line and clamp the extremes", () => {
    expect([markerRadius(250), markerRadius(1), markerRadius(2000), markerRadius(null)]).toEqual([
      RADIUS_AT_250,
      MIN_RADIUS,
      MAX_RADIUS,
      MIN_RADIUS,
    ]);
  });
});

it("writes numbers only beside the highest few Severe forecasts, so a city-wide episode stays readable", () => {
  // Given: seven stations, six above 250, one of them selected (its name label takes that spot)
  const values = new Map<string, number | null>([["a", 260], ["b", 400], ["c", 300], ["d", 120], ["e", 500], ["f", 350], ["g", 280]]);
  // When / Then: the top three, excluding the selected station, highest first
  expect(valueLabels([...values.keys()], (slug) => values.get(slug) ?? null, "e")).toEqual(["b", "f", "c"]);
});

it("draws big dots first so small ones stay visible, and the selected station last", () => {
  // Given: forecasts of 100, 300 and none; station a is selected
  const values = new Map<string, number | null>([["a", 100], ["b", 300], ["c", null]]);
  const stations = [{ slug: "a" }, { slug: "b" }, { slug: "c" }];
  // When / Then
  expect(drawOrder(stations, (slug) => values.get(slug) ?? null, "a").map((station) => station.slug)).toEqual(["b", "c", "a"]);
});
