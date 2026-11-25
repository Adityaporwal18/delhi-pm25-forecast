import { describe, expect, it } from "vitest";
import { METRES_PER_UG, columnHeight, columnRows, rgb, tooltipText } from "./columns3d";

const STATIONS = [
  { slug: "a", name: "Anand Vihar, Delhi - DPCC", latitude: 28.65, longitude: 77.32 },
  { slug: "b", name: "Bawana, Delhi - DPCC", latitude: 28.78, longitude: 77.05 },
];

describe("3D columns", () => {
  it("are as tall as the forecast, in proportion, and flat without one", () => {
    // Given: forecasts of 100 and 200 µg/m³, and none
    // When / Then: twice the value is twice the height; no forecast, no column
    expect([columnHeight(100), columnHeight(200), columnHeight(null)]).toEqual([100 * METRES_PER_UG, 200 * METRES_PER_UG, 0]);
  });

  it("take their colour from the CPCB hex colour", () => {
    expect(rgb("#ff9900")).toEqual([255, 153, 0]);
  });

  it("are built only for stations with a forecast, at the station, in its category colour", () => {
    // Given: two stations, only Anand Vihar forecast
    const points = new Map([["a", { slug: "a", p10: 47, p50: 85, p90: 166, measured: null, colour: "#ffff00", category: "Moderate" }]]);
    // When / Then
    expect(columnRows(STATIONS, points)).toEqual([
      { slug: "a", name: "Anand Vihar", position: [77.32, 28.65], value: 85, low: 47, high: 166, colour: [255, 255, 0], category: "Moderate" },
    ]);
  });

  it("are described in words in their tooltip, rounded to whole µg/m³", () => {
    // Given: a column; When: hovered; Then: the value, the band and the category
    const row = { name: "Anand Vihar", value: 85.4, low: 47.2, high: 166, category: "Moderate" };
    expect(tooltipText(row)).toBe("Anand Vihar: 85 µg/m³ (80% band 47–166), Moderate");
  });
});
