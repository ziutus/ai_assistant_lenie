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

  it("names the checked feed and shows new items in a feed_check result", async () => {
    const feedJob = {
      ...bridgeJob, id: "feed-job", type: "feed_check", status: "done", attempt: 1,
      result: { checked: 1, items: 15, new_items: 4, errors: [], feeds: [{ feed_source_id: 7, feed_name: "Zaufana Trzecia Strona", items: 15, new_items: 4 }] },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ jobs: [feedJob], capabilities: {}, total: 1 }), { status: 200 })));
    render(<AuthorizationContext.Provider value={auth}><Jobs /></AuthorizationContext.Provider>);

    expect(await screen.findByText("źródło: Zaufana Trzecia Strona · new_items: 4 · items: 15 · errors: 0")).toBeTruthy();
  });

  it("lists the titles of new feed items and the auto-import count", async () => {
    const feedJob = {
      ...bridgeJob, id: "feed-job", type: "feed_check", status: "done", attempt: 1,
      result: {
        checked: 1, items: 15, new_items: 2, errors: [], import: { imported: 2, errors: [] },
        feeds: [{
          feed_source_id: 2, feed_name: "Na Wschód od Bliskiego Wschodu", items: 15, new_items: 2,
          new_entries: [
            { feed_item_id: 12306, title: "#867 Francja płonie", url: "https://www.youtube.com/watch?v=SbVIPk5YoAM", status: "new" },
            { feed_item_id: 12307, title: "Drugi odcinek", url: "https://www.youtube.com/watch?v=abc", status: "new" },
          ],
          new_entries_truncated: 1,
        }],
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ jobs: [feedJob], capabilities: {}, total: 1 }), { status: 200 })));
    render(<AuthorizationContext.Provider value={auth}><Jobs /></AuthorizationContext.Provider>);

    const link = await screen.findByRole("link", { name: "#867 Francja płonie" });
    expect(link.getAttribute("href")).toBe("https://www.youtube.com/watch?v=SbVIPk5YoAM");
    expect(screen.getByText("…i 1 więcej")).toBeTruthy();
    expect(screen.getByText(/zaimportowano: 2/)).toBeTruthy();
  });

  it("lets a user start the bridge without exposing management actions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ jobs: [bridgeJob], capabilities: { manage_jobs: false, run_legacy_aws_pull: true }, total: 1 }), { status: 200 })));
    render(<AuthorizationContext.Provider value={auth}><Jobs /></AuthorizationContext.Provider>);

    await screen.findByText("legacy_aws_pull");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.getByRole("button", { name: "Uruchom legacy_aws_pull" })).toBeTruthy();
  });
});
