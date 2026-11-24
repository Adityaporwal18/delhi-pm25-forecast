/** Design tokens used from TypeScript (map and chart); the same values as DESIGN.md and styles.css. */
export const TOKENS = {
  ink950: "#150f23",
  ink850: "#261c3d",
  ink800: "#362d59",
  ink600: "#79628c",
  violet300: "#a99cf0",
  band: "rgba(106, 95, 193, 0.35)",
  text: "#ffffff",
  textSubtle: "#b9b1cc",
  measured: "#ffffff",
  /** Ring around stations forecast above 250 µg/m³ (Severe); brighter than the maroon fill so it reads on the dark map. */
  severeRing: "#ff5a5a",
} as const;
