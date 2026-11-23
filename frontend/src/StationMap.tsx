import "leaflet/dist/leaflet.css";
import { latLngBounds } from "leaflet";
import { useEffect } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { MapPoint, Station } from "./api";
import { TOKENS } from "./tokens";

const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** `quiet`: the station has no reading for the forecast hour (live view); drawn with a dashed outline. */
type Marker = MapPoint & { quiet?: boolean };

interface Props {
  stations: readonly Station[];
  points: ReadonlyMap<string, Marker>;
  selected: string;
  onSelect: (slug: string) => void;
  active: boolean;
}

/** A map whose tab was hidden must re-measure its box when shown again (the window may have changed size). */
function KeepSized({ active }: { active: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (active) {
      map.invalidateSize();
    }
  }, [active, map]);
  return null;
}

function describe(point: Marker | undefined): string {
  if (point === undefined || point.p50 === null) {
    return "no forecast";
  }
  const quiet = point.quiet === true ? " · no current PM2.5 reading" : "";
  return `${point.p50} µg/m³ (80% band ${point.p10 ?? "?"}–${point.p90 ?? "?"}), ${point.category ?? ""}${quiet}`;
}

export function StationMap({ stations, points, selected, onSelect, active }: Props) {
  const bounds = latLngBounds(stations.map((station): [number, number] => [station.latitude, station.longitude]));
  return (
    <MapContainer bounds={bounds} boundsOptions={{ padding: [24, 24] }} className="map" scrollWheelZoom>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution={ATTRIBUTION} maxZoom={19} />
      <KeepSized active={active} />
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
              ...(point?.quiet === true ? { dashArray: "3 3", weight: isSelected ? 3 : 2, color: isSelected ? TOKENS.text : TOKENS.textSubtle } : {}),
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
