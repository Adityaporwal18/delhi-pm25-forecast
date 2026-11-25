import { Deck, type MapViewState, type PickingInfo, WebMercatorViewport } from "@deck.gl/core";
import { TileLayer } from "@deck.gl/geo-layers";
import { BitmapLayer, ColumnLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { useEffect, useMemo, useRef, useState } from "react";
import type { MapPoint, Station } from "./api";
import { type ColumnRow, type Rgb, columnHeight, columnRows, rgb, tooltipText } from "./columns3d";
import { valueLabels } from "./markers";
import { TOKENS } from "./tokens";

const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const INK = rgb(TOKENS.ink);
const PAPER = rgb(TOKENS.paperHi);
const SMOG: Rgb = [142, 27, 18];
/** Multiplied into the desaturated tiles: warm paper greys, like the 2D map. */
const TINT: Rgb = [246, 239, 225];
const TOOLTIP_STYLE = {
  backgroundColor: TOKENS.paperHi,
  color: TOKENS.ink,
  border: `1px solid ${TOKENS.ink}`,
  borderRadius: "0",
  fontFamily: "Atkinson Hyperlegible, sans-serif",
  fontSize: "13px",
  padding: "4px 8px",
};

interface Props {
  stations: readonly Station[];
  points: ReadonlyMap<string, MapPoint>;
  selected: string;
  onSelect: (slug: string) => void;
}

function isColumn(value: unknown): value is ColumnRow {
  return typeof value === "object" && value !== null && "slug" in value && "position" in value;
}

/** Every station in view with headroom above for tall columns, then tilted 45° and turned a little.
 * The tilt flattens the network to about 0.7 of its height on screen, so the fit zooms back in. */
function startView(stations: readonly Station[], size: { width: number; height: number }): MapViewState {
  const lons = stations.map((station) => station.longitude);
  const lats = stations.map((station) => station.latitude);
  const fitted = new WebMercatorViewport({ width: Math.max(size.width, 1), height: Math.max(size.height, 1) }).fitBounds(
    [
      [Math.min(...lons), Math.min(...lats)],
      [Math.max(...lons), Math.max(...lats)],
    ],
    { padding: { top: 56, bottom: 44, left: 24, right: 24 } },
  );
  return { longitude: fitted.longitude, latitude: fitted.latitude, zoom: fitted.zoom + 0.15, pitch: 45, bearing: -12 };
}

function basemap() {
  return new TileLayer<ImageBitmap>({
    id: "basemap",
    data: TILES,
    minZoom: 0,
    maxZoom: 19,
    tileSize: 256,
    renderSubLayers: (props) => {
      const [low, high] = props.tile.boundingBox;
      return new BitmapLayer({
        id: `${props.id}-image`,
        image: props.data,
        bounds: [low[0] ?? 0, low[1] ?? 0, high[0] ?? 0, high[1] ?? 0],
        desaturate: 1,
        tintColor: TINT,
      });
    },
  });
}

function layers(rows: readonly ColumnRow[], selected: string, labelled: ReadonlySet<string>) {
  const chosen = rows.filter((row) => row.slug === selected);
  const tagged = rows.filter((row) => row.slug === selected || labelled.has(row.slug));
  return [
    basemap(),
    new ScatterplotLayer<ColumnRow>({
      id: "feet",
      data: rows,
      getPosition: (row) => row.position,
      getRadius: 6,
      radiusUnits: "pixels",
      getFillColor: (row) => row.colour,
      stroked: true,
      getLineColor: INK,
      lineWidthMinPixels: 1,
    }),
    new ScatterplotLayer<ColumnRow>({
      id: "selected-ring",
      data: chosen,
      getPosition: (row) => row.position,
      getRadius: 11,
      radiusUnits: "pixels",
      filled: false,
      stroked: true,
      getLineColor: INK,
      lineWidthMinPixels: 2.5,
    }),
    new ColumnLayer<ColumnRow>({
      id: "columns",
      data: rows,
      diskResolution: 20,
      radius: 4.5,
      radiusUnits: "pixels",
      extruded: true,
      pickable: true,
      autoHighlight: true,
      highlightColor: [...rgb(TOKENS.accent), 220],
      getPosition: (row) => row.position,
      getElevation: (row) => columnHeight(row.value),
      getFillColor: (row) => [...row.colour, 245],
      material: { ambient: 0.62, diffuse: 0.5, shininess: 18, specularColor: [70, 64, 56] },
    }),
    new TextLayer<ColumnRow>({
      id: "labels",
      data: tagged,
      getPosition: (row) => [row.position[0], row.position[1], columnHeight(row.value) + 300],
      getText: (row) => (row.slug === selected ? `${row.name} · ${Math.round(row.value)}` : String(Math.round(row.value))),
      getColor: (row) => (row.slug === selected ? INK : SMOG),
      getSize: 13,
      fontFamily: "Atkinson Hyperlegible, sans-serif",
      fontWeight: 700,
      characterSet: "auto",
      background: true,
      getBackgroundColor: [...PAPER, 245],
      getBorderColor: INK,
      getBorderWidth: 1,
      backgroundPadding: [5, 2],
      getAlignmentBaseline: "bottom",
      getPixelOffset: [0, -6],
    }),
  ];
}

/** The forecast as columns on a tilted map. Loaded only when the reader switches to 3D. */
export function Map3D({ stations, points, selected, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const deck = useRef<Deck | null>(null);
  const home = useRef<MapViewState | null>(null);
  const select = useRef(onSelect);
  const [failure, setFailure] = useState<string | null>(null);
  select.current = onSelect;
  const rows = useMemo(() => columnRows(stations, points), [stations, points]);
  const labelled = useMemo(
    () => new Set(valueLabels(rows.map((row) => row.slug), (slug) => points.get(slug)?.p50 ?? null, selected)),
    [rows, points, selected],
  );

  useEffect(() => {
    const parent = host.current;
    if (parent === null) {
      return undefined;
    }
    const view = startView(stations, parent.getBoundingClientRect());
    home.current = view;
    try {
      deck.current = new Deck({
        parent,
        initialViewState: view,
        controller: { inertia: true },
        useDevicePixels: Math.min(window.devicePixelRatio, 2),
        pickingRadius: 6,
        getTooltip: (info: PickingInfo) => (isColumn(info.object) ? { text: tooltipText(info.object), style: TOOLTIP_STYLE } : null),
        onClick: (info: PickingInfo) => {
          if (isColumn(info.object)) {
            select.current(info.object.slug);
          }
        },
        onError: (error: Error) => setFailure(error.message),
      });
    } catch (error) {
      setFailure(error instanceof Error ? error.message : String(error));
    }
    return () => {
      deck.current?.finalize();
      deck.current = null;
    };
  }, [stations]);

  useEffect(() => {
    deck.current?.setProps({ layers: layers(rows, selected, labelled) });
  }, [rows, selected, labelled]);

  if (failure !== null) {
    return (
      <div className="map3d map3d-error">
        <p className="warning">The 3D view needs WebGL, which this browser could not start ({failure}). The 2D map shows everything.</p>
      </div>
    );
  }
  return (
    <div className="map3d" ref={host}>
      <button
        type="button"
        className="button map3d-note"
        onClick={() => home.current !== null && deck.current?.setProps({ initialViewState: { ...home.current } })}
        title="Drag to move · right-drag or two fingers to tilt and turn"
      >
        Reset view
      </button>
    </div>
  );
}
