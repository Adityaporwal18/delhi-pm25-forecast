import "leaflet/dist/leaflet.css";
import { latLngBounds } from "leaflet";
import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";
import type { MapPoint, Station } from "./api";
import { TOKENS } from "./tokens";

const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

interface Props {
  stations: readonly Station[];
  points: ReadonlyMap<string, MapPoint>;
  selected: string;
  onSelect: (slug: string) => void;
}

function describe(point: MapPoint | undefined): string {
  if (point === undefined || point.p50 === null) {
    return "no forecast";
  }
  return `${point.p50} µg/m³ (80% band ${point.p10 ?? "?"}–${point.p90 ?? "?"}), ${point.category ?? ""}`;
}

export function StationMap({ stations, points, selected, onSelect }: Props) {
  const bounds = latLngBounds(stations.map((station): [number, number] => [station.latitude, station.longitude]));
  return (
    <MapContainer bounds={bounds} boundsOptions={{ padding: [24, 24] }} className="map" scrollWheelZoom>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution={ATTRIBUTION} maxZoom={19} />
      {stations.map((station) => {
        const point = points.get(station.slug);
        const isSelected = station.slug === selected;
        return (
          <CircleMarker
            key={station.slug}
            center={[station.latitude, station.longitude]}
            radius={isSelected ? 11 : 8}
            pathOptions={{
              color: isSelected ? TOKENS.text : TOKENS.ink950,
              weight: isSelected ? 3 : 1.5,
              fillColor: point?.colour ?? TOKENS.ink600,
              fillOpacity: 0.95,
            }}
            eventHandlers={{ click: () => onSelect(station.slug) }}
          >
            <Tooltip>{`${station.name}: ${describe(point)}`}</Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
