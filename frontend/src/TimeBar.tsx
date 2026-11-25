import { useEffect, useState } from "react";
import { STEP_MS, nextHour, playFrom } from "./playback";

/** Plays the map through the forecast hours, one step per STEP_MS, and stops at the last hour.
 * A step waits until the shown hour's data is `ready`, so the label never runs ahead of the dots;
 * playback stops when the view is hidden. Values jump between hours: nothing is tweened, because
 * an in-between frame would show values that were never forecast. */
interface PlaybackInput {
  hours: readonly number[];
  hour: number;
  setHour: (hour: number) => void;
  ready: boolean;
  active: boolean;
}

export function usePlayback({ hours, hour, setHour, ready, active }: PlaybackInput) {
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing || !ready) {
      return undefined;
    }
    const next = nextHour(hours, hour);
    if (next === null) {
      setPlaying(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setHour(next), STEP_MS);
    return () => window.clearTimeout(timer);
  }, [playing, ready, hours, hour, setHour]);
  useEffect(() => {
    if (!active) {
      setPlaying(false);
    }
  }, [active]);
  function toggle() {
    if (!playing) {
      setHour(playFrom(hours, hour));
    }
    setPlaying(!playing);
  }
  function choose(chosen: number) {
    setPlaying(false);
    setHour(chosen);
  }
  return { playing, toggle, choose };
}

interface Props {
  hours: readonly number[];
  hour: number;
  /** The Delhi time the shown hour stands for, e.g. "Wed 25 Nov 2026, 02:00". */
  when: string;
  playing: boolean;
  onToggle: () => void;
  onChoose: (hour: number) => void;
}

/** Laid over the top of the map: play/pause, the hour now shown (always visible) and a scrubber. */
export function TimeBar({ hours, hour, when, playing, onToggle, onChoose }: Props) {
  const index = Math.max(0, hours.indexOf(hour));
  return (
    <div className="time-bar" role="group" aria-label="Forecast hour shown on the map">
      <button
        type="button"
        className="play"
        onClick={onToggle}
        aria-label={playing ? "Pause" : "Play through the forecast hours"}
        title={playing ? "Pause" : "Play"}
      >
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
          {playing ? <path d="M4 3h3v10H4zM9 3h3v10H9z" /> : <path d="M4.5 2.5v11l9-5.5z" />}
        </svg>
      </button>
      <p className="hour-label">
        <strong>+{hour} h</strong>
        <span>{when}</span>
      </p>
      <div className="scrubber">
        <input
          type="range"
          min={0}
          max={hours.length - 1}
          step={1}
          value={index}
          aria-label="Hours ahead"
          aria-valuetext={`${hour} hours ahead, ${when}`}
          onChange={(event) => onChoose(hours[Number(event.target.value)] ?? hour)}
        />
        <div className="ticks" aria-hidden="true">
          {hours.map((option) => (
            <span key={option} className={option === hour ? "on" : undefined}>
              {option}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
