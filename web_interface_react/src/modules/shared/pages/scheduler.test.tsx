import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
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

const schedulerResponse = (capabilities = { manage_jobs: true, run_legacy_aws_pull: true, run_feed_daily: true }) => ({
  generated_at: "2026-07-30T10:00:00Z",
  schedules: [{ id: "feed_daily", job_type: "feed_daily", enabled: true, description: "Import feedów", timezone: "Europe/Warsaw", times: ["04:00"], schedule: "04:00", next_run_at: "2026-07-31T04:00:00+02:00", last_job: { id: "job-1", status: "done", finished_at: "2026-07-30T04:02:00Z" } }],
  capabilities,
});

describe("Scheduler", () => {
  it("shows configured schedules and their latest jobs", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(schedulerResponse()), { status: 200 })));

    render(<AuthorizationContext.Provider value={auth}><Scheduler /></AuthorizationContext.Provider>);

    expect(await screen.findByText("feed_daily")).toBeTruthy();
    expect(screen.getAllByText("Włączony")).toHaveLength(2);
    expect(screen.getByText("04:00")).toBeTruthy();
  });

  it("lets a service key manually enqueue a scheduled job", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(schedulerResponse()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "manual-job", status: "queued" }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(schedulerResponse()), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AuthorizationContext.Provider value={auth}><Scheduler /></AuthorizationContext.Provider>);

    const runButton = await screen.findByText("Uruchom teraz") as HTMLButtonElement;
    expect(runButton.disabled).toBe(false);
    fireEvent.click(runButton);

    expect(await screen.findByText(/manual-job/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/jobs", expect.objectContaining({
      method: "POST", body: JSON.stringify({ type: "feed_daily" }),
    }));
  });

  it("disables the button when the key lacks the capability", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(schedulerResponse({ manage_jobs: false, run_legacy_aws_pull: true, run_feed_daily: false })), { status: 200 })));

    render(<AuthorizationContext.Provider value={auth}><Scheduler /></AuthorizationContext.Provider>);

    const runButton = await screen.findByText("Uruchom teraz") as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
  });
});
