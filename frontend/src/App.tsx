import { type ReactNode, useState } from "react";
import { type Accuracy, type Meta, fetchAccuracy, fetchMeta } from "./api";
import { LiveView } from "./LiveView";
import { ReplayView } from "./ReplayView";
import { Status, useLoad } from "./useLoad";

type Mode = "live" | "accuracy";

const MODES: readonly { mode: Mode; label: string }[] = [
  { mode: "live", label: "Live" },
  { mode: "accuracy", label: "Accuracy (2025 replay)" },
];

const LIVE_NOTE =
  "Live forecast for the next 48 hours, refreshed about every 3 hours. Colours are a PM2.5-based category (CPCB PM2.5 " +
  "bands, which CPCB defines on 24-hour averages), not AQI.";

function initialMode(): Mode {
  return window.location.hash === "#accuracy" ? "accuracy" : "live";
}

function Page({ children }: { children: ReactNode }) {
  return <div className="page">{children}</div>;
}

export function App() {
  const [meta, retryMeta] = useLoad(fetchMeta, "meta");
  const [accuracy, retryAccuracy] = useLoad(fetchAccuracy, "accuracy");
  if (meta.state !== "ready") {
    return (
      <Page>
        <Status load={meta} what="the stations" retry={retryMeta} />
      </Page>
    );
  }
  if (accuracy.state !== "ready") {
    return (
      <Page>
        <Status load={accuracy} what="the accuracy numbers" retry={retryAccuracy} />
      </Page>
    );
  }
  return <Shell meta={meta.data} accuracy={accuracy.data} />;
}

function Shell({ meta, accuracy }: { meta: Meta; accuracy: Accuracy }) {
  const [mode, setMode] = useState<Mode>(initialMode);
  // A tab is mounted the first time it is opened and then kept, hidden when inactive, so
  // switching back shows its data and choices at once instead of loading them again.
  const [opened, setOpened] = useState<ReadonlySet<Mode>>(() => new Set([initialMode()]));

  function choose(next: Mode) {
    setMode(next);
    setOpened((before) => new Set(before).add(next));
    window.history.replaceState(null, "", `#${next}`);
  }

  return (
    <Page>
      <header className="header">
        <div>
          <h1 className="title">
            Delhi PM2.5 forecast <span className="title-soft">— 48 hours ahead</span>
          </h1>
          <p className="caption">
            {meta.stations.length} CPCB monitoring stations ·{" "}
            {mode === "live" ? "live forecast, refreshed about every 3 hours" : "replay of the held-out 2025 test year"}
          </p>
        </div>
        <div className="segmented mode-switch" role="group" aria-label="View">
          {MODES.map((item) => (
            <button key={item.mode} type="button" aria-pressed={item.mode === mode} onClick={() => choose(item.mode)}>
              {item.label}
            </button>
          ))}
        </div>
      </header>
      {opened.has("live") && (
        <div hidden={mode !== "live"}>
          <LiveView meta={meta} accuracy={accuracy} active={mode === "live"} />
        </div>
      )}
      {opened.has("accuracy") && (
        <div hidden={mode !== "accuracy"}>
          <ReplayView meta={meta} accuracy={accuracy} active={mode === "accuracy"} />
        </div>
      )}
      <footer className="footer">
        <p>{mode === "live" ? LIVE_NOTE : meta.note}</p>
        <p>{meta.credits}</p>
      </footer>
    </Page>
  );
}
