import "leaflet/dist/leaflet.css";
import { divIcon, latLngBounds } from "leaflet";
import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { MapPoint, Station } from "./api";
import { drawOrder, labelSide, markerRadius, valueLabels } from "./markers";
import { TOKENS } from "./tokens";

const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const SEVERE = "Severe";

/** `quiet`: the station has no reading for the forecast hour (live view); drawn with a dashed outline. */
type Dot = MapPoint & { quiet?: boolean };

interface Props {
  stations: readonly Station[];
  points: ReadonlyMap<string, Dot>;
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

function describe(point: Dot | undefined): string {
  if (point === undefined || point.p50 === null) {
    return "no forecast";
  }
  const quiet = point.quiet === true ? " · no current PM2.5 reading" : "";
  return `${Math.round(point.p50)} µg/m³ (80% band ${Math.round(point.p10 ?? 0)}–${Math.round(point.p90 ?? 0)}), ${point.category ?? ""}${quiet}`;
}

interface LabelSpec {
  text: string;
  kind: "value" | "name";
  offset: number;
  side: "left" | "right";
}

/** A text label beside a dot, as a DOM element (textContent, so names can never inject HTML). */
function textIcon({ text, kind, offset, side }: LabelSpec) {
  const span = document.createElement("span");
  span.className = `map-label ${kind} ${side}`;
  span.textContent = text;
  span.style.setProperty("--offset", `${offset}px`);
  return divIcon({ html: span, className: "map-label-anchor", iconSize: [0, 0], iconAnchor: [0, 0] });
}

function Label({ at, text, kind, offset, side }: LabelSpec & { at: [number, number] }) {
  const icon = useMemo(() => textIcon({ text, kind, offset, side }), [text, kind, offset, side]);
  return <Marker position={at} icon={icon} interactive={false} keyboard={false} />;
}

export function StationMap({ stations, points, selected, onSelect, active }: Props) {
  const bounds = useMemo(
    () => latLngBounds(stations.map((station): [number, number] => [station.latitude, station.longitude])),
    [stations],
  );
  const valueOf = (slug: string) => points.get(slug)?.p50 ?? null;
  const ordered = drawOrder(stations, valueOf, selected);
  const labelled = new Set(valueLabels(stations.map((station) => station.slug), valueOf, selected));
  const span = { west: bounds.getWest(), east: bounds.getEast() };
  return (
    <MapContainer bounds={bounds} boundsOptions={{ padding: [20, 20] }} zoomSnap={0.25} className="map" scrollWheelZoom>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution={ATTRIBUTION} maxZoom={19} />
      <KeepSized active={active} />
      {ordered.map((station) => {
        const point = points.get(station.slug);
        const at: [number, number] = [station.latitude, station.longitude];
        const radius = markerRadius(point?.p50 ?? null);
        const severe = point?.category === SEVERE && point.p50 !== null;
        const isSelected = station.slug === selected;
        return (
          <span key={station.slug}>
            {severe && (
              <CircleMarker
                center={at}
                radius={radius + 5}
                interactive={false}
                className="severe-halo"
                pathOptions={{ color: TOKENS.severeRing, weight: 2, fill: false }}
              />
            )}
            <CircleMarker
              center={at}
              radius={radius}
              pathOptions={{
                color: TOKENS.ink,
                weight: 1.5,
                fillColor: point?.colour ?? TOKENS.paperLo,
                fillOpacity: 0.9,
                ...(point?.quiet === true ? { dashArray: "3 3", weight: 2, color: TOKENS.ink } : {}),
              }}
              eventHandlers={{ click: () => onSelect(station.slug) }}
            >
              <Tooltip>{`${station.name}: ${describe(point)}`}</Tooltip>
            </CircleMarker>
            {isSelected && (
              <CircleMarker center={at} radius={radius + 4} interactive={false} pathOptions={{ color: TOKENS.ink, weight: 2.5, fill: false }} />
            )}
            {severe && labelled.has(station.slug) && point.p50 !== null && (
              <Label at={at} text={String(Math.round(point.p50))} kind="value" offset={radius + 7} side={labelSide(station.longitude, span)} />
            )}
            {isSelected && (
              <Label at={at} text={station.name.split(",")[0] ?? station.name} kind="name" offset={radius + 8} side={labelSide(station.longitude, span)} />
            )}
          </span>
        );
      })}
    </MapContainer>
  );
}
