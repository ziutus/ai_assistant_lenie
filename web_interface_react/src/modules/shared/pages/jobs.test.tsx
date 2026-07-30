import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AuthorizationState } from "../../../types";
import { AuthorizationContext } from "../context/authorizationContext";
import Jobs from "./jobs";

const auth: AuthorizationState = {
  apiUrl: "http://api.test", apiKey: "service-key", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};

const bridgeJob = {
  id: "bridge-job", type: "legacy_aws_pull", status: "failed", attempt: 1, max_attempts: 3,
  created_at: "2026-07-29T15:00:00Z", started_at: "2026-07-29T15:01:00Z", finished_at: "2026-07-29T15:02:00Z",
  watermark: "2026-07-29T15:25:35+00:00", result: { found: 6, added: 0, skipped: 6, errors: 0 },
};

describe("Jobs", () => {
  it("shows bridge observability data and service-only actions", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ jobs: [bridgeJob], capabilities: { manage_jobs: true, run_legacy_aws_pull: true }, total: 51 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "bridge-job", status: "queued" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ jobs: [bridgeJob], capabilities: { manage_jobs: true, run_legacy_aws_pull: true }, total: 51 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AuthorizationContext.Provider value={auth}><Jobs /></AuthorizationContext.Provider>);

    expect(await screen.findByText("2026-07-29T15:25:35+00:00")).toBeTruthy();
    const jobCell = screen.getAllByText("legacy_aws_pull").find((element) => element.tagName === "TD");
    if (!jobCell) throw new Error("job row not found");
    fireEvent.click(jobCell);
    expect(jobCell.closest("tr")?.style.background).toBe("rgb(219, 234, 254)");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("http://api.test/jobs/bridge-job/retry", expect.objectContaining({ method: "POST" })));
    expect(screen.getAllByRole("button", { name: "Następna" })).toHaveLength(2);
  });

  it("lets a user start the bridge without exposing management actions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ jobs: [bridgeJob], capabilities: { manage_jobs: false, run_legacy_aws_pull: true }, total: 1 }), { status: 200 })));
    render(<AuthorizationContext.Provider value={auth}><Jobs /></AuthorizationContext.Provider>);

    await screen.findByText("legacy_aws_pull");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.getByRole("button", { name: "Uruchom legacy_aws_pull" })).toBeTruthy();
  });
});
