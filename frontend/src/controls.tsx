import type { Meta, Station } from "./api";

/** Anand Vihar, one of Delhi's most polluted stations, is shown first when it exists. */
export function defaultStation(meta: Meta): string {
  return meta.stations.find((station) => station.slug === "anand_vihar_dpcc")?.slug ?? meta.stations[0]?.slug ?? "";
}

interface StationProps {
  stations: readonly Station[];
  value: string;
  onChange: (slug: string) => void;
}

/** The keyboard-friendly alternative to clicking a station on the map. */
export function StationSelect({ stations, value, onChange }: StationProps) {
  const sorted = [...stations].sort((a, b) => a.name.localeCompare(b.name));
  return (
    <label className="field">
      <span>Station</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {sorted.map((option) => (
          <option key={option.slug} value={option.slug}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}
