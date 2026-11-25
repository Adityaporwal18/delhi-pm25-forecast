/** Each forecast hour stays on screen this long while playing: a full sweep of the 8 hours takes 7 seconds. */
export const STEP_MS = 1000;

/** The hours the map can show. Horizon 0 is the value measured now, not a forecast, so it is left out. */
export function mapHours(horizons: readonly number[]): number[] {
  return horizons.filter((hours) => hours > 0);
}

/** The hour after `current` while playing, or null at the last hour: playback stops there instead of
 * looping, so the final frame stays readable and nothing moves until asked. */
export function nextHour(hours: readonly number[], current: number): number | null {
  const index = hours.indexOf(current);
  return index >= 0 ? (hours[index + 1] ?? null) : null;
}

/** Where Play starts: the first hour if the sweep has already reached the end, otherwise where it is. */
export function playFrom(hours: readonly number[], current: number): number {
  return nextHour(hours, current) === null ? (hours[0] ?? current) : current;
}
