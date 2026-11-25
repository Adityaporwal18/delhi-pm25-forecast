import { type ReactNode, Suspense, lazy, useState } from "react";
import type { Category, MapPoint, Station } from "./api";
import { Legend, type MapView } from "./Legend";
import { StationMap } from "./StationMap";
import { TimeBar, type TimeBarProps } from "./TimeBar";

/** deck.gl is about 0.25 MB compressed, so it is fetched only when the reader switches to 3D. */
const Map3D = lazy(() => import("./Map3D").then((module) => ({ default: module.Map3D })));

interface Props {
  stations: readonly Station[];
  categories: readonly Category[];
  points: ReadonlyMap<string, MapPoint & { quiet?: boolean }>;
  selected: string;
  onSelect: (slug: string) => void;
  active: boolean;
  timeBar: TimeBarProps;
  status?: ReactNode;
}

/** The map block shared by both views: time bar, colour key, then the map, 2D or 3D. */
export function MapPanel({ stations, categories, points, selected, onSelect, active, timeBar, status }: Props) {
  const [view, setView] = useState<MapView>("2d");
  return (
    <section className="panel map-panel" aria-label="Map of monitoring stations">
      <TimeBar {...timeBar} />
      <Legend categories={categories} view={view} onView={setView} />
      <div className="map-frame">
        {view === "2d" ? (
          <StationMap stations={stations} points={points} selected={selected} onSelect={onSelect} active={active} />
        ) : (
          <Suspense fallback={<p className="status">Loading the 3D view…</p>}>
            <Map3D stations={stations} points={points} selected={selected} onSelect={onSelect} />
          </Suspense>
        )}
        {status}
      </div>
    </section>
  );
}
