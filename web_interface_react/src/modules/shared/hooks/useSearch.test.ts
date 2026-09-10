import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import axios from "axios";
import { buildNaturalSearchPayload, useSearch } from "./useSearch";
import { emptySearchCriteria } from "../utils/searchCriteria";

vi.mock("axios");

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

describe("Search telemetry context", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(axios.post).mockReset();
  });

  it("preserves AI provenance through manual correction and paging back to the first page", async () => {
    const criteria = { ...emptySearchCriteria("war"), languages: ["pl"], author_name: "Author" };
    vi.mocked(axios.post).mockResolvedValue({ data: {
      search_id: 123, interpretation: criteria, results: [], status: "parsed", fallback_used: false,
    } });
    const { result } = renderHook(() => useSearch());
    result.current.telemetry.manual("query");
    await act(async () => { await result.current.handleSearch("war by Author", "10"); });
    const first = vi.mocked(axios.post).mock.calls[0][1] as any;
    expect(first.telemetry.action).toBe("submit");
    expect(first.telemetry.requested_mode).toBe("natural");
    expect(first.telemetry.changed_fields).toEqual(["query"]);
    result.current.telemetry.manual("languages");
    const corrected = { ...criteria, languages: ["en"] };
    const correction = result.current.telemetry.next("correction", "explicit");
    await act(async () => { await result.current.handleExplicitSearch(corrected, "10", 0, correction); });
    const second = vi.mocked(axios.post).mock.calls[1][1] as any;
    expect(second.telemetry.criteria_origin).toMatchObject({ languages: "manual", author_name: "ai" });
    expect(second.telemetry.changed_fields).toEqual(["languages"]);
    const page = result.current.telemetry.next("page_change", "natural");
    await act(async () => { await result.current.handleExplicitSearch(corrected, "10", 0, page); });
    const third = vi.mocked(axios.post).mock.calls[2][1] as any;
    expect(third.telemetry.action).toBe("page_change");
    expect(third.telemetry.browse_id).toBe(second.telemetry.browse_id);
    expect(third.telemetry.event_id).not.toBe(second.telemetry.event_id);
    expect(third.telemetry.changed_fields).toEqual([]);
    await act(async () => { await result.current.sendFeedback("partially_correct", corrected, {
      ...result.current.telemetry.next("correction", "explicit"), changed_fields: correction.changed_fields,
    }); });
    const feedback = vi.mocked(axios.post).mock.calls[3][1] as any;
    expect(feedback.telemetry.action).toBe("correction");
    expect(feedback.telemetry.changed_fields).toEqual(["languages"]);
    expect(feedback.telemetry.session_id).toBe(first.telemetry.session_id);
    result.current.telemetry.manual("author_name");
    await act(async () => { await result.current.sendFeedback("correct"); });
    const confirmation = vi.mocked(axios.post).mock.calls[4][1] as any;
    expect(confirmation.telemetry.requested_mode).toBe("natural");
    expect(confirmation.telemetry.changed_fields).toEqual([]);
    expect([...result.current.telemetry.pending]).toEqual(["author_name"]);
  });
});
