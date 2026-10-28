import React from "react";
import { MemoryRouter } from "react-router-dom";
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
  render(<MemoryRouter><AuthorizationContext.Provider value={auth}><Feeds /></AuthorizationContext.Provider></MemoryRouter>);
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

  it("renames a feed from the edit form", async () => {
    const renamed = { ...feed, name: "News 2" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ feed_sources: [feed] }))
      .mockResolvedValueOnce(json({ content_groups: [] }))
      .mockResolvedValueOnce(json(renamed))
      .mockResolvedValueOnce(json({ feed_sources: [renamed] }))
      .mockResolvedValueOnce(json({ content_groups: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><AuthorizationContext.Provider value={auth}><Feeds /></AuthorizationContext.Provider></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Edytuj" }));
    expect((screen.getByLabelText("Nazwa") as HTMLInputElement).value).toBe("News");
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(screen.getByText("Nazwa feedu jest wymagana.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: " News 2 " } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(await screen.findByText("Zapisano zmiany.")).toBeTruthy();
    expect(screen.getByText("News 2")).toBeTruthy();
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toMatchObject({ name: "News 2" });
    expect(fetchMock.mock.calls[2][0]).toBe("http://api.test/feed_sources/1");
  });
});

function setupFeeds(initial = "/feeds") {
  let rows = [{ ...feed, tags: ["aws"] }, { ...feed, id: 2, name: "Other", tags: ["aws"], disabled: true }];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.includes("content_groups")) return json({ content_groups: [] });
    if (init?.method) {
      const body = JSON.parse(String(init.body));
      const targets = url.endsWith("bulk-disable") ? rows.filter(row => body.tag ? row.tags.includes(body.tag) : body.feed_ids.includes(row.id)) : rows.filter(row => url.endsWith(`/${row.id}`));
      const changed = targets.filter(row => row.disabled !== body.disabled).map(row => row.id);
      rows = rows.map(row => changed.includes(row.id) ? { ...row, disabled: body.disabled } : row);
      return json(url.endsWith("bulk-disable") ? { changed: changed.length, feed_ids: changed } : rows[0]);
    }
    const params = new URL(url).searchParams;
    const matching = rows.filter(row => !params.has("tag") || params.getAll("tag").some(tag => row.tags.includes(tag)));
    return json({ feed_sources: matching.filter(row => !params.has("disabled") || row.disabled === (params.get("disabled") === "1")), counts: { active: matching.filter(row => !row.disabled).length, disabled: matching.filter(row => row.disabled).length }, tags: [{ tag: "aws", count: 2 }] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter initialEntries={[initial]}><AuthorizationContext.Provider value={auth}><Feeds /></AuthorizationContext.Provider></MemoryRouter>);
  return fetchMock;
}

it("defaults to active and toggles a card with undo", async () => {
  const fetchMock = setupFeeds();
  expect(await screen.findByText("News")).toBeTruthy();
  expect(screen.queryByText("Other")).toBeNull();
  expect(fetchMock.mock.calls[0][0]).toContain("disabled=0");
  fireEvent.click(screen.getByRole("button", { name: "Aktywny" }));
  await waitFor(() => expect(screen.queryByText("News")).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "Cofnij" }));
  expect(await screen.findByText("News")).toBeTruthy();
});

it("selects visible cards and undoes only changed IDs", async () => {
  const fetchMock = setupFeeds("/feeds?status=all");
  await screen.findByText("Other");
  fireEvent.click(screen.getByLabelText("Zaznacz wszystkie widoczne"));
  fireEvent.click(screen.getByRole("button", { name: "Wyłącz zaznaczone (2)" }));
  await screen.findByText(/Zmieniono 1 feedów/);
  await waitFor(() => expect((screen.getByRole("button", { name: "Cofnij" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Cofnij" }));
  await screen.findByText("Cofnięto zmiany.");
  const mutations = fetchMock.mock.calls.filter(([, init]) => init?.method);
  expect(JSON.parse(String(mutations[1][1]?.body))).toEqual({ disabled: false, feed_ids: [1] });
});

it("confirms tag actions with counts across statuses and permits cancellation", async () => {
  const fetchMock = setupFeeds("/feeds?tag=aws");
  const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValue(true);
  vi.stubGlobal("confirm", confirm);
  const enable = await screen.findByRole("button", { name: "Włącz wszystkie z tagiem aws (1)" });
  fireEvent.click(enable);
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method)).toHaveLength(0);
  fireEvent.click(enable);
  expect(confirm).toHaveBeenLastCalledWith("Włączyć wszystkie feedy z tagiem aws (1)?");
  expect(await screen.findByText("Other")).toBeTruthy();
});

it("normalizes tags in the add payload", async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(json({ feed_sources: [], content_groups: [] })));
  vi.stubGlobal("fetch", fetchMock);
  await openAdd();
  fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: "Tagged" } });
  fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://example.com/feed" } });
  fireEvent.change(screen.getByLabelText(/Tagi/), { target: { value: " aws, gcp,aws, , " } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await screen.findByText("Dodano feed.");
  expect(JSON.parse(fetchMock.mock.calls[2][1].body).tags).toEqual(["aws", "gcp"]);
});

it("combines URL status and tag filters with name search", async () => {
  const fetchMock = setupFeeds("/feeds?status=disabled&tag=aws&tag=gcp");
  expect(await screen.findByText("Other")).toBeTruthy();
  expect(fetchMock.mock.calls[0][0]).toContain("disabled=1&tag=aws&tag=gcp");
  expect(screen.queryByText("News")).toBeNull();
  fireEvent.change(screen.getByLabelText("Szukaj po nazwie"), { target: { value: "missing" } });
  expect(screen.queryByText("Other")).toBeNull();
  fireEvent.change(screen.getByLabelText("Szukaj po nazwie"), { target: { value: "oth" } });
  expect(screen.getByText("Other")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Wszystkie (2)" }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.endsWith("feed_sources?tag=aws&tag=gcp"))).toBe(true));
});
