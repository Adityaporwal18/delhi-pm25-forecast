import type { Category } from "./api";
import { MAX_RADIUS, markerRadius } from "./markers";

const SIZE_SAMPLES = [50, 150, 300] as const;

function range(categories: readonly Category[], index: number): string {
  const lower = index === 0 ? 0 : (categories[index - 1]?.upper_ug_m3 ?? 0);
  const upper = categories[index]?.upper_ug_m3 ?? null;
  return upper === null ? `above ${lower}` : `${lower}–${upper}`;
}

/** The colour key, laid over the map's bottom-left corner so its caveat stays in view. */
export function Legend({ categories }: { categories: readonly Category[] }) {
  return (
    <section className="map-legend" aria-labelledby="legend-title">
      <h2 id="legend-title" className="overline">
        PM2.5-based category <span className="unit">(µg/m³)</span>
      </h2>
      <ul>
        {categories.map((category, index) => (
          <li key={category.label}>
            <span className="swatch" style={{ background: category.colour }} aria-hidden="true" />
            <span>{category.label}</span>
            <span className="range">{range(categories, index)}</span>
          </li>
        ))}
      </ul>
      <div className="size-key" aria-label="Dot area is proportional to the forecast">
        {SIZE_SAMPLES.map((value) => (
          <span key={value} className="size-sample">
            <svg width={2 * MAX_RADIUS} height={2 * MAX_RADIUS} aria-hidden="true">
              <circle cx={MAX_RADIUS} cy={MAX_RADIUS} r={markerRadius(value)} className="size-dot" />
            </svg>
            {value}
          </span>
        ))}
        <span className="size-note">dot area ∝ forecast · red ring: above 250 (top 3 numbered) · dashed: no current reading</span>
      </div>
      <p className="caption">
        CPCB defines these bands on 24-hour averages; here they colour hourly forecasts. This is not the AQI.
      </p>
    </section>
  );
}
