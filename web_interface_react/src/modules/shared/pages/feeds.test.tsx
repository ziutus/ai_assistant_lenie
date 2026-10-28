import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthorizationState } from "../../../types";
import { AuthorizationContext } from "../context/authorizationContext";
import Feeds from "./feeds";

const auth: AuthorizationState = {
  apiUrl: "http://api.test", apiKey: "user-key", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
const feed = {
  id: 1, name: "News", type: "rss", url: "https://example.com/feed", channel_id: null,
  author_name: null, language: "pl", tags: [], default_topic_group_ids: [],
  auto_import: false, auto_import_after: null, disabled: false, default_state: "URL_ADDED",
  last_checked_at: null, last_error: null,
};

async function openAdd() {
  render(<AuthorizationContext.Provider value={auth}><Feeds /></AuthorizationContext.Provider>);
  await screen.findByText("Brak feedów.");
  fireEvent.click(screen.getByRole("button", { name: "Dodaj feed" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("Feeds", () => {
  it("opens the add form with defaults and requires a nonblank name", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(json({ feed_sources: [], content_groups: [] })));
    vi.stubGlobal("fetch", fetchMock);
    await openAdd();
    expect((screen.getByLabelText("Typ") as HTMLSelectElement).value).toBe("rss");
    expect((screen.getByLabelText("Język") as HTMLInputElement).value).toBe("pl");
    expect((screen.getByLabelText("Automatyczny import") as HTMLInputElement).checked).toBe(false);
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
    expect(screen.getByText("Nazwa feedu jest wymagana.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Anuluj" }));
    expect(screen.queryByLabelText("Nazwa")).toBeNull();
  });

  it("posts the trimmed payload and reloads the list", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ feed_sources: [] }))
      .mockResolvedValueOnce(json({ content_groups: [] }))
      .mockResolvedValueOnce(json(feed, 201))
      .mockResolvedValueOnce(json({ feed_sources: [feed] }))
      .mockResolvedValueOnce(json({ content_groups: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await openAdd();
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: " News " } });
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: " https://example.com/feed " } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
    expect(await screen.findByText("Dodano feed.")).toBeTruthy();
    expect(screen.getByText("News")).toBeTruthy();
    expect(screen.queryByLabelText("Nazwa")).toBeNull();
    expect(fetchMock).toHaveBeenNthCalledWith(3, "http://api.test/feed_sources", {
      method: "POST", headers: { "x-api-key": "user-key", "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "News", type: "rss", url: "https://example.com/feed", channel_id: null,
        language: "pl", tags: [], author_name: null, default_topic_group_ids: [],
        auto_import: false, auto_import_after: null, disabled: false, default_state: "URL_ADDED",
      }),
    });
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("validates the source and displays a duplicate-name response", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ feed_sources: [] }))
      .mockResolvedValueOnce(json({ content_groups: [] }))
      .mockResolvedValueOnce(json({ message: "feed with this name already exists" }, 409));
    vi.stubGlobal("fetch", fetchMock);
    await openAdd();
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: "News" } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
    expect(screen.getByText("URL feedu jest wymagany.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Typ"), { target: { value: "youtube_channel" } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
    expect(screen.getByText("ID kanału YouTube jest wymagane.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.change(screen.getByLabelText("ID kanału"), { target: { value: " UC123 " } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
    expect(await screen.findByText("feed with this name already exists")).toBeTruthy();
    expect(screen.getByLabelText("Nazwa")).toBeTruthy();
    const payload = JSON.parse(fetchMock.mock.calls[2][1].body);
    expect(payload).toMatchObject({ channel_id: "UC123", url: null, author_name: null });
    await waitFor(() => expect((screen.getByRole("button", { name: "Dodaj" }) as HTMLButtonElement).disabled).toBe(false));
  });
});
