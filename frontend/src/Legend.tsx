import type { Category } from "./api";

function range(categories: readonly Category[], index: number): string {
  const lower = index === 0 ? 0 : (categories[index - 1]?.upper_ug_m3 ?? 0);
  const upper = categories[index]?.upper_ug_m3 ?? null;
  return upper === null ? `above ${lower}` : `${lower}–${upper}`;
}

export function Legend({ categories }: { categories: readonly Category[] }) {
  return (
    <section className="panel legend" aria-labelledby="legend-title">
      <h2 id="legend-title" className="heading">
        PM2.5-based category (µg/m³)
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
      <p className="caption">
        CPCB defines these bands on 24-hour averages; here they colour hourly forecasts. This is not the AQI.
      </p>
    </section>
  );
}
