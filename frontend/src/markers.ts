/** Map dots: area in proportion to the forecast (radius ∝ √µg/m³), anchored at the Severe line. */
export const RADIUS_AT_250 = 13;
export const MIN_RADIUS = 4;
export const MAX_RADIUS = 21;

/** Clamped so faint values stay visible and the rare extreme does not swamp the map. A station
 * without a forecast gets the smallest dot (it is drawn grey). */
export function markerRadius(value: number | null): number {
  if (value === null) {
    return MIN_RADIUS;
  }
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, RADIUS_AT_250 * Math.sqrt(Math.max(value, 0) / 250)));
}

export const SEVERE_LINE = 250;
export const MAX_VALUE_LABELS = 3;

/** Which Severe stations get their number written on the map: the highest few, skipping the
 * selected station (it already carries its name label). Every Severe dot still gets the ring. */
export function valueLabels(slugs: readonly string[], value: (slug: string) => number | null, selected: string): string[] {
  return slugs
    .filter((slug) => slug !== selected && (value(slug) ?? 0) > SEVERE_LINE)
    .sort((a, b) => (value(b) ?? 0) - (value(a) ?? 0))
    .slice(0, MAX_VALUE_LABELS);
}

/** Labels of stations in the eastern third of the map go on the left of the dot, so a name beside
 * an eastern station (Anand Vihar, on the city's edge) is not cut off by the map's edge. */
export function labelSide(longitude: number, span: { west: number; east: number }): "left" | "right" {
  return longitude > span.east - (span.east - span.west) / 3 ? "left" : "right";
}

/** Largest forecast first, so smaller dots are drawn on top and stay visible; the selected station
 * last of all, so its ring is never hidden. */
export function drawOrder<T extends { slug: string }>(stations: readonly T[], value: (slug: string) => number | null, selected: string): T[] {
  const size = (station: T) => (station.slug === selected ? -Infinity : (value(station.slug) ?? 0));
  return [...stations].sort((a, b) => size(b) - size(a));
}
