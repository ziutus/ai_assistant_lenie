import { describe, expect, it } from "vitest";
import { buildNaturalSearchPayload } from "./useSearch";

describe("buildNaturalSearchPayload", () => {
  it("uses the new natural_query contract and numeric limit", () => {
    expect(buildNaturalSearchPayload("  teksty o gospodarce po 2004  ", "30")).toEqual({
      natural_query: "teksty o gospodarce po 2004",
      limit: 30,
    });
  });

  it("does not leak legacy website_similar fields", () => {
    const payload = buildNaturalSearchPayload("wojna", "10") as Record<string, unknown>;
    expect(payload.search).toBeUndefined();
    expect(payload.period_from).toBeUndefined();
    expect(payload.translate).toBeUndefined();
  });
});
