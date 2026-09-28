import { describe, expect, it } from "vitest";
import { formatEventDateRange } from "./contactEventDate";

describe("formatEventDateRange", () => {
  it.each([undefined, null, "", "2026-09-27"])("formats a single date with end %s", end => {
    expect(formatEventDateRange("2026-09-27", end)).toBe("27.09.2026");
  });

  it.each([
    ["2026-09-27", "2026-09-29", "27-29.09.2026"],
    ["2026-09-27", "2026-10-02", "27.09-02.10.2026"],
    ["2026-12-30", "2027-01-02", "30.12.2026-02.01.2027"],
  ])("formats %s through %s", (start, end, expected) => {
    expect(formatEventDateRange(start, end)).toBe(expected);
  });
});
