import { describe, expect, it } from "vitest";
import { addHours, delhiDate, delhiHour, delhiLabel, findIssueTime } from "./time";

// Given: 02:30 UTC on 1 Nov 2025 is 08:00 in Delhi (UTC+5:30)
const ISSUED = "2025-11-01T02:30:00Z";

describe("Delhi time helpers", () => {
  it("label the moment in Delhi time", () => {
    expect(delhiLabel(ISSUED)).toBe("Sat 1 Nov 2025, 08:00");
  });

  it("give the Delhi calendar date for a date input", () => {
    expect(delhiDate("2025-12-31T19:30:00Z")).toBe("2026-01-01");
  });

  it("give the Delhi clock hour", () => {
    expect(delhiHour(ISSUED)).toBe(8);
  });

  it("give the moment a forecast hour stands for, crossing midnight in Delhi", () => {
    // When: 18 hours after the 08:00 issue; Then: 02:00 the next day
    expect(delhiLabel(addHours(ISSUED, 18))).toBe("Sun 2 Nov 2025, 02:00");
  });

  it("find the issue time for a Delhi date and hour, or nothing", () => {
    const times = ["2025-11-01T02:30:00Z", "2025-11-01T14:30:00Z"];
    expect([findIssueTime(times, "2025-11-01", 20), findIssueTime(times, "2025-11-02", 8)]).toEqual([
      "2025-11-01T14:30:00Z",
      undefined,
    ]);
  });
});
