import type { MapPoint, Station } from "./api";
import { ug } from "./Focal";

/** Column height per µg/m³, in metres: 100 µg/m³ stands 4 km tall and 300 µg/m³ 12 km, about a
 * third of the station network's width, so typical and Severe columns both read at the default tilt. */
export const METRES_PER_UG = 40;

export type Rgb = [number, number, number];

export interface ColumnRow {
  slug: string;
  name: string;
  position: [number, number];
  value: number;
  low: number | null;
  high: number | null;
  colour: Rgb;
  category: string | null;
}

/** Linear in the forecast, so heights compare honestly; no forecast, no column. */
export function columnHeight(value: number | null): number {
  return value === null ? 0 : Math.max(value, 0) * METRES_PER_UG;
}

export function rgb(hex: string): Rgb {
  const channel = (start: number) => Number.parseInt(hex.slice(start, start + 2), 16);
  return [channel(1), channel(3), channel(5)];
}

export function columnRows(stations: readonly Station[], points: ReadonlyMap<string, MapPoint>): ColumnRow[] {
  return stations.flatMap((station) => {
    const point = points.get(station.slug);
    if (point === undefined || point.p50 === null) {
      return [];
    }
    return [
      {
        slug: station.slug,
        name: station.name.split(",")[0] ?? station.name,
        position: [station.longitude, station.latitude],
        value: point.p50,
        low: point.p10,
        high: point.p90,
        colour: rgb(point.colour ?? "#e9e3d5"),
        category: point.category,
      },
    ];
  });
}

export function tooltipText(row: Pick<ColumnRow, "name" | "value" | "low" | "high" | "category">): string {
  return `${row.name}: ${ug(row.value)} µg/m³ (80% band ${ug(row.low)}–${ug(row.high)})${row.category === null ? "" : `, ${row.category}`}`;
}
