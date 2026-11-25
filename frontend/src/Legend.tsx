import type { Category } from "./api";

export type MapView = "2d" | "3d";

function range(categories: readonly Category[], index: number): string {
  const lower = index === 0 ? 0 : (categories[index - 1]?.upper_ug_m3 ?? 0);
  const upper = categories[index]?.upper_ug_m3 ?? null;
  return upper === null ? `above ${lower}` : `${lower}–${upper}`;
}

const ENCODING: Record<MapView, string> = {
  "2d": "Dot area ∝ forecast · red ring: above 250 (top 3 numbered) · dashed outline: no current reading.",
  "3d": "Column height ∝ forecast; the disc at its foot marks the station. Perspective shrinks far columns, so compare values in 2D.",
};

interface Props {
  categories: readonly Category[];
  view: MapView;
  onView: (view: MapView) => void;
}

/** The colour key and the 2D/3D switch, between the time bar and the map: it never covers a station. */
export function Legend({ categories, view, onView }: Props) {
  return (
    <section className="legend" aria-labelledby="legend-title">
      <div className="legend-head">
        <h2 id="legend-title" className="kicker">
          PM2.5-based category <span className="unit">(µg/m³, hourly)</span>
        </h2>
        <div className="view-switch" role="group" aria-label="Map view">
          <button type="button" aria-pressed={view === "2d"} onClick={() => onView("2d")}>
            2D map
          </button>
          <button type="button" aria-pressed={view === "3d"} onClick={() => onView("3d")} title="Loads about 0.25 MB the first time">
            3D
          </button>
        </div>
      </div>
      <ol className="scale">
        {categories.map((category, index) => (
          <li key={category.label}>
            <span className="scale-bar" style={{ background: category.colour }} aria-hidden="true" />
            <span className="scale-name">{category.label}</span>
            <span className="scale-range">{range(categories, index)}</span>
          </li>
        ))}
      </ol>
      <p className="legend-notes">
        {ENCODING[view]} CPCB defines these bands on 24-hour averages; here they colour hourly forecasts.{" "}
        <strong>This is not the AQI.</strong>
      </p>
    </section>
  );
}
