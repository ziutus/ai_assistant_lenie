import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AuthorizationState } from "../../../types";
import { AuthorizationContext } from "../context/authorizationContext";
import Scheduler from "./scheduler";

const auth: AuthorizationState = {
  apiUrl: "http://api.test", apiKey: "service-key", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};

describe("Scheduler", () => {
  it("shows configured schedules and their latest jobs", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      generated_at: "2026-07-30T10:00:00Z",
      schedules: [{ id: "feed_daily", job_type: "feed_daily", enabled: true, description: "Import feedów", timezone: "Europe/Warsaw", times: ["04:00"], schedule: "04:00", next_run_at: "2026-07-31T04:00:00+02:00", last_job: { id: "job-1", status: "done", finished_at: "2026-07-30T04:02:00Z" } }],
    }), { status: 200 })));

    render(<AuthorizationContext.Provider value={auth}><Scheduler /></AuthorizationContext.Provider>);

    expect(await screen.findByText("feed_daily")).toBeTruthy();
    expect(screen.getAllByText("Włączony")).toHaveLength(2);
    expect(screen.getByText("04:00")).toBeTruthy();
  });
});
