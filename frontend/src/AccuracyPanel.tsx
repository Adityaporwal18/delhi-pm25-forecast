import type { Accuracy } from "./api";

/** "expected": quoted in the live view; "measured": shown with the 2025 replay it was measured on. */
type Framing = "expected" | "measured";

const TITLE: Record<Framing, string> = {
  expected: "Expected accuracy",
  measured: "Accuracy in the held-out 2025 test year",
};

const SOURCE: Record<Framing, string> = {
  expected:
    "Based on held-out 2025 testing of the evaluation model (trained on 2023–2024). It is not a measurement of this " +
    "forecast: the live models use the same recipe trained on data up to 2026, and have no held-out year of their own.",
  measured: "Measured over 2025, a year the evaluation model never saw while training. These are the forecasts this replay shows.",
};

function one(value: number): string {
  return value.toFixed(1);
}

export function AccuracyPanel({ accuracy, framing }: { accuracy: Accuracy; framing: Framing }) {
  const at48 = accuracy.horizons.find((horizon) => horizon.horizon_h === 48);
  const at6 = accuracy.horizons.find((horizon) => horizon.horizon_h === 6);
  const smog = accuracy.smoggiest_10pct_48h;
  if (at48 === undefined) {
    return null;
  }
  return (
    <section className="panel" aria-labelledby={`accuracy-${framing}`}>
      <h2 id={`accuracy-${framing}`} className="heading">
        {TITLE[framing]}
      </h2>
      <p className="caption">{SOURCE[framing]}</p>
      <ul className="facts">
        <li>
          <span className="fact">{one(at48.model_mae)}</span> µg/m³ average error 48 hours ahead
          {at6 === undefined ? "" : ` (${one(at6.model_mae)} at 6 hours)`}. The seasonal average is off by{" "}
          {one(at48.climatology_mae)}, “same as now” by {one(at48.persistence_mae)}.
        </li>
        <li>
          <span className="fact">{one(at48.inside_band_pct)}%</span> of measured values fell inside the 80% band, 48 hours
          ahead.
        </li>
      </ul>
      <p className="warning">
        <strong>Heavy smog:</strong> in the smoggiest 10% of 2025 hours the 80% band held only{" "}
        <strong>{one(at48.inside_band_smoggiest_10pct)}%</strong> of measured values, and 48-hour forecasts were too low by{" "}
        <strong>{one(Math.abs(smog.model_bias))} µg/m³</strong> on average (average error {one(smog.model_mae)}, against{" "}
        {one(smog.climatology_mae)} for the seasonal average).
      </p>
    </section>
  );
}
