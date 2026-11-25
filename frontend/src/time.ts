/** Delhi-time helpers. The API speaks UTC; people in Delhi read Delhi time (UTC+5:30, no DST). */
const DELHI = "Asia/Kolkata";

const LABEL = new Intl.DateTimeFormat("en-GB", {
  timeZone: DELHI,
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const DATE = new Intl.DateTimeFormat("en-GB", { timeZone: DELHI, year: "numeric", month: "2-digit", day: "2-digit" });
const HOUR = new Intl.DateTimeFormat("en-GB", { timeZone: DELHI, hour: "2-digit", hourCycle: "h23" });

function parts(format: Intl.DateTimeFormat, isoUtc: string): (type: Intl.DateTimeFormatPartTypes) => string {
  const pieces = format.formatToParts(new Date(isoUtc));
  return (type) => pieces.find((piece) => piece.type === type)?.value ?? "";
}

/** "Sat 1 Nov 2025, 08:00" */
export function delhiLabel(isoUtc: string): string {
  const part = parts(LABEL, isoUtc);
  return `${part("weekday")} ${part("day")} ${part("month")} ${part("year")}, ${part("hour")}:${part("minute")}`;
}

/** "2025-11-01", the format of an <input type="date">. */
export function delhiDate(isoUtc: string): string {
  const part = parts(DATE, isoUtc);
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function addHours(isoUtc: string, hours: number): string {
  return new Date(Date.parse(isoUtc) + hours * 3_600_000).toISOString();
}

export function delhiHour(isoUtc: string): number {
  return Number(parts(HOUR, isoUtc)("hour"));
}

/** The issue time on a Delhi date at a Delhi clock hour, if the replay has one. */
export function findIssueTime(times: readonly string[], date: string, hour: number): string | undefined {
  return times.find((time) => delhiDate(time) === date && delhiHour(time) === hour);
}
