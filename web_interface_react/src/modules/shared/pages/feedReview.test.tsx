import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import FeedReview from "./feedReview";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas:5000", apiKey: "test-key" }) };
});
vi.mock("../components/OpenRouterBalance/openRouterBalance", () => ({ default: () => null }));

const feedItem = {
  id: 7, feed_source_id: 1, title: "Artykuł testowy", url: "https://example.com/a", summary: null,
  published_at: null, status: "new", saved_at: null, saved_by_user_id: null,
  review_note: "Interesuje mnie ta inicjatywa.",
};

function jsonResponse(body: object) {
  return new Response(JSON.stringify(body), { status: 200 });
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/discussion_summary")) return Promise.resolve(jsonResponse({ open: 3, done: 1 }));
    if (url.endsWith("/discussion") && init?.method === "PATCH") return Promise.resolve(jsonResponse({
      ...feedItem, llm_discussion_status: JSON.parse(String(init.body)).status,
    }));
    if (url.endsWith("/note") && init?.method === "PATCH") return Promise.resolve(jsonResponse({ ...feedItem, review_note: JSON.parse(String(init.body)).note }));
    if (url.includes("/feed_items?")) return Promise.resolve(jsonResponse({ feed_items: [feedItem], total: 1 }));
    if (url.endsWith("/feed_sources")) return Promise.resolve(jsonResponse({ feed_sources: [{ id: 1, name: "Blog", type: "rss", disabled: false }] }));
    if (url.endsWith("/content_groups")) return Promise.resolve(jsonResponse({ content_groups: [] }));
    if (url.endsWith("/content_group_model")) return Promise.resolve(jsonResponse({ default_model: "gpt-4o-mini", models: [] }));
    if (url.endsWith("/groups") || url.endsWith("/group-suggestions")) return Promise.resolve(jsonResponse({ groups: [], suggestions: [] }));
    // Any action: the network is gone (VPN dropped) — fetch rejects with TypeError.
    return Promise.reject(new TypeError("Failed to fetch"));
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows the discussion count and flags a card independently of its text decision", async () => {
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  await screen.findByRole("tab", { name: "Do omówienia (3)" });
  const article = (await screen.findByText(feedItem.title)).closest("article") as HTMLElement;
  fireEvent.click(within(article).getByRole("checkbox", { name: "Do omówienia z LLM" }));
  await within(article).findByText("💬 Do omówienia");
  expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith("/7/discussion")
    && init?.method === "PATCH" && init.body === JSON.stringify({ status: "open" }))).toBe(true);
  expect(within(article).getByRole("button", { name: "Do przeczytania" })).toBeTruthy();
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/discussion_summary"))).toHaveLength(2));
});

it("reviews discussion across text statuses, saves a result and advances to the next item", async () => {
  let remaining = [
    { ...feedItem, status: "skipped", llm_discussion_status: "open" },
    { ...feedItem, id: 8, title: "Drugi do omówienia", llm_discussion_status: "open" },
  ];
  const fallback = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (String(url).includes("/feed_items?")) return jsonResponse({ feed_items: remaining, total: remaining.length });
    if (String(url).endsWith("/discussion") && init?.method === "PATCH") {
      const updated = { ...remaining[0], llm_discussion_status: JSON.parse(String(init.body)).status };
      remaining = remaining.slice(1);
      return jsonResponse(updated);
    }
    return fallback(url, init);
  });
  render(<MemoryRouter initialEntries={["/feed-review?view=discuss"]}><FeedReview /></MemoryRouter>);
  const article = (await screen.findByText(feedItem.title)).closest("article") as HTMLElement;
  const request = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes("/feed_items?"))!;
  expect(new URL(String(request[0])).searchParams.get("discussion")).toBe("open");
  expect(new URL(String(request[0])).searchParams.has("status")).toBe(false);
  expect(within(article).getByText("Status tekstu: Pominięty")).toBeTruthy();
  expect(within(article).queryByRole("button", { name: /Zaimportuj|Pomiń|Ignoruj|Zachowaj|Przywróć/ })).toBeNull();
  fireEvent.change(within(article).getByLabelText("Wynik (link lub krótka notatka, opcjonalnie)"), { target: { value: "https://example.com/result" } });
  fireEvent.click(within(article).getByRole("button", { name: "Omówione" }));
  await screen.findByText("Drugi do omówienia");
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.body === JSON.stringify({ status: "done", result: "https://example.com/result" }))).toBe(true);
  expect(screen.getByText("Wpis czeka też na decyzję w zakładce Nowe.")).toBeTruthy();
  fireEvent.click(screen.getByRole("checkbox", { name: "Do omówienia z LLM" }));
  await screen.findByText("Brak wpisów do omówienia.");
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.body === JSON.stringify({ status: null }))).toBe(true);
});

it("lets an item in the discussion queue be filed under topics too", async () => {
  const fallback = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (String(url).includes("/feed_items?")) return jsonResponse({ feed_items: [{ ...feedItem, status: "skipped", llm_discussion_status: "open" }], total: 1 });
    return fallback(url, init);
  });
  render(<MemoryRouter initialEntries={["/feed-review?mode=single&view=discuss&item=7"]}><FeedReview /></MemoryRouter>);
  const article = (await screen.findByText(feedItem.title)).closest("article") as HTMLElement;
  expect(within(article).getByText("Status tekstu: Pominięty")).toBeTruthy();
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/feed_items/7/groups"))).toBe(true));
  expect(within(article).getByRole("button", { name: /Edytuj|Zmień|kategori|temat/i })).toBeTruthy();
});

it("opens the done queue and reopens an item with its saved result", async () => {
  let done = true;
  const fallback = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (String(url).includes("/feed_items?")) return jsonResponse({ feed_items: done ? [{
      ...feedItem, status: "saved_for_later", llm_discussion_status: "done", llm_discussion_result: "https://example.com/result",
    }] : [], total: done ? 1 : 0 });
    if (String(url).endsWith("/discussion") && init?.method === "PATCH") {
      done = false;
      return jsonResponse({ ...feedItem, llm_discussion_status: "open" });
    }
    return fallback(url, init);
  });
  render(<MemoryRouter initialEntries={["/feed-review?view=discuss&discussion=done&mode=all"]}><FeedReview /></MemoryRouter>);
  const article = (await screen.findByText(feedItem.title)).closest("article") as HTMLElement;
  expect(within(article).getByRole("link", { name: "https://example.com/result" }).getAttribute("href")).toBe("https://example.com/result");
  expect(within(article).getByText("✅ Omówione")).toBeTruthy();
  expect(within(article).queryByRole("button", { name: /Zaimportuj|Przywróć/ })).toBeNull();
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("discussion=done"))).toBe(true);
  fireEvent.click(within(article).getByRole("button", { name: "Otwórz ponownie" }));
  await screen.findByText("Brak omówionych wpisów.");
});

it("shows a connection error on the item when saving for later fails to reach the API", async () => {
  render(<MemoryRouter initialEntries={["/feed-review"]}><FeedReview /></MemoryRouter>);
  const article = (await screen.findByText("Artykuł testowy")).closest("article") as HTMLElement;
  fireEvent.click(within(article).getByRole("button", { name: "Do przeczytania" }));
  const alert = await within(article).findByRole("alert");
  expect(alert.textContent).toContain("Nie można połączyć się z API http://nas:5000");
  expect(alert.textContent).toContain("NIE została zapisana");
  expect(within(article).getByRole("button", { name: "Do przeczytania" })).toHaveProperty("disabled", false);
});

it("reports a timeout when the API never answers", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    vi.mocked(fetch).mockImplementation((url, init) => {
      const u = String(url);
      if (u.includes("/feed_items?")) return Promise.resolve(jsonResponse({ feed_items: [feedItem], total: 1 }));
      if (u.endsWith("/feed_sources")) return Promise.resolve(jsonResponse({ feed_sources: [] }));
      if (u.endsWith("/content_groups")) return Promise.resolve(jsonResponse({ content_groups: [] }));
      // Packets silently dropped: the request only ends when aborted.
      return new Promise((_, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
    });
    render(<MemoryRouter initialEntries={["/feed-review"]}><FeedReview /></MemoryRouter>);
    const article = (await screen.findByText("Artykuł testowy")).closest("article") as HTMLElement;
    fireEvent.click(within(article).getByRole("button", { name: "Do przeczytania" }));
    expect(within(article).getByText("Zapisywanie…")).toBeTruthy();
    await vi.advanceTimersByTimeAsync(20_000);
    const alert = await within(article).findByRole("alert");
    expect(alert.textContent).toContain("Brak odpowiedzi z API");
  } finally {
    vi.useRealTimers();
  }
});

it("shows a fixed, dismissible error when changing page fails", async () => {
  vi.mocked(fetch).mockImplementation((url) => {
    const u = String(url);
    if (u.includes("/feed_items?") && u.includes("offset=0")) return Promise.resolve(jsonResponse({ feed_items: [feedItem], total: 500 }));
    if (u.endsWith("/groups") || u.endsWith("/group-suggestions")) return Promise.resolve(jsonResponse({ groups: [], suggestions: [] }));
    if (u.endsWith("/feed_sources")) return Promise.resolve(jsonResponse({ feed_sources: [] }));
    if (u.endsWith("/content_groups")) return Promise.resolve(jsonResponse({ content_groups: [] }));
    return Promise.reject(new TypeError("Failed to fetch"));
  });
  render(<MemoryRouter initialEntries={["/feed-review"]}><FeedReview /></MemoryRouter>);
  await screen.findByText("Artykuł testowy");
  fireEvent.click(screen.getByRole("button", { name: "Następny →" }));
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Nie można połączyć się z API");
  expect(alert.style.position).toBe("fixed");
  fireEvent.click(within(alert).getByRole("button", { name: "Zamknij komunikat" }));
  expect(screen.queryByRole("alert")).toBeNull();
});

it("defaults to single mode and requests suggestions when the selected model changes", async () => {
  const model = "openrouter/google/gemini-2.5-flash-lite";
  localStorage.setItem("lenie_feedReviewFilters", JSON.stringify({ feedSourceId: "", view: "new" }));
  const second = { ...feedItem, id: 8, title: "Drugi wpis" };
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("/feed_items?")) return jsonResponse({ feed_items: [feedItem, second], total: 2 });
    if (u.endsWith("/feed_sources")) return jsonResponse({ feed_sources: [] });
    if (u.endsWith("/content_group_model")) return jsonResponse({ default_model: model, models: [
      { id: model, label: "Gemini", external: true }, { id: "gpt-4o-mini", label: "GPT" },
    ] });
    if (u.endsWith("/content_groups")) return jsonResponse({ content_groups: [{ id: 1, kind: "topic", name: "AI" }] });
    if (u.endsWith("/group-suggestions")) return jsonResponse(init?.method === "POST" ? { run: { status: "queued" } } : { run: null, suggestions: [] });
    return jsonResponse({ groups: [] });
  });
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  await screen.findByText("Artykuł testowy");
  const posts = () => vi.mocked(fetch).mock.calls.filter(([url, init]) => String(url).endsWith("/group-suggestions") && init?.method === "POST");
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(posts()[0][1]?.body).toBe(JSON.stringify({ model }));
  expect(screen.queryByText("Drugi wpis")).toBeNull();
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/feed_items/8/"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Następny →" }));
  await screen.findByText("Drugi wpis");
  await waitFor(() => expect(posts()).toHaveLength(2));
  expect(screen.queryByText("Artykuł testowy")).toBeNull();
  fireEvent.change(screen.getByLabelText("Model do podpowiadania tematów"), { target: { value: "gpt-4o-mini" } });
  await waitFor(() => expect(posts()).toHaveLength(3));
  expect(posts()[2][1]?.body).toBe(JSON.stringify({ model: "gpt-4o-mini" }));

});

it("crosses page boundaries and lands on the previous page's last item", async () => {
  vi.mocked(fetch).mockImplementation(async url => {
    const u = String(url);
    if (u.includes("/feed_items?")) {
      const offset = Number(new URL(u).searchParams.get("offset"));
      return jsonResponse({ feed_items: Array.from({ length: offset ? 1 : 50 }, (_, i) => ({ ...feedItem, id: offset + i + 1, title: `Wpis testowy ${offset + i + 1}` })), total: 51 });
    }
    if (u.endsWith("/content_group_model")) return jsonResponse({ default_model: "gpt-4o-mini", models: [] });
    return jsonResponse({ feed_sources: [], content_groups: [], groups: [], suggestions: [] });
  });
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  await screen.findByText("Wpis testowy 1");
  for (let i = 0; i < 50; i++) fireEvent.click(screen.getByRole("button", { name: "Następny →" }));
  await screen.findByText("Wpis testowy 51");
  expect(screen.getByText("Wpis 51 z 51")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Następny →" })).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByRole("button", { name: "← Poprzedni" }));
  await screen.findByText("Wpis testowy 50");
  expect(screen.getByText("Wpis 50 z 51")).toBeTruthy();
}, 15000);

it("advances after saving an item and shows the empty queue after the last action", async () => {
  let remaining = [feedItem, { ...feedItem, id: 8, title: "Drugi wpis" }];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("/feed_items?")) return jsonResponse({ feed_items: remaining, total: remaining.length });
    if (init?.method === "POST" && u.endsWith("/save-for-later")) {
      remaining = remaining.slice(1);
      return jsonResponse({});
    }
    if (u.endsWith("/content_group_model")) return jsonResponse({ default_model: "gpt-4o-mini", models: [] });
    return jsonResponse({ feed_sources: [], content_groups: [], groups: [], suggestions: [] });
  });
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  await screen.findByText("Artykuł testowy");
  fireEvent.click(screen.getByRole("button", { name: "Do przeczytania" }));
  await screen.findByText("Drugi wpis");
  expect(screen.getByText("Wpis 1 z 1")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Do przeczytania" }));
  await screen.findByText("Brak nowych wpisów dla wybranego źródła.");
  expect(screen.queryByRole("article")).toBeNull();
});


function Location() { return <output data-testid="location">{useLocation().search}</output>; }

it("edits item comments in both modes and on the later tab", async () => {
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  const label = "Komentarz dla LLM: co mnie zainteresowało i co z tym zrobić";
  const textarea = await screen.findByLabelText(label);
  expect(textarea).toHaveProperty("value", feedItem.review_note);
  fireEvent.change(textarea, { target: { value: "Stwórz zalążek dokumentu." } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz komentarz" }));
  await screen.findByText("Zapisano komentarz.");
  expect(textarea).toHaveProperty("value", "Stwórz zalążek dokumentu.");
  expect(fetch).toHaveBeenCalledWith("http://nas:5000/feed_items/7/note", expect.objectContaining({
    method: "PATCH", body: JSON.stringify({ note: "Stwórz zalążek dokumentu." }),
  }));
  fireEvent.click(screen.getByRole("button", { name: "Wszystkie na liście" }));
  expect(screen.getByLabelText(label)).toHaveProperty("value", "Stwórz zalążek dokumentu.");
  fireEvent.click(screen.getByRole("button", { name: "Po jednym wpisie" }));
  expect(screen.getByLabelText(label)).toHaveProperty("value", "Stwórz zalążek dokumentu.");
  fireEvent.click(screen.getByRole("tab", { name: "Do przeczytania / obejrzenia" }));
  await waitFor(() => expect(screen.getByLabelText(label)).toHaveProperty("value", feedItem.review_note));
});

it("switches modes in the URL, remembers all mode, and suggests every list item", async () => {
  const model = "gpt-4o-mini";
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("/feed_items?")) return jsonResponse({ feed_items: [feedItem, { ...feedItem, id: 8, title: "Second" }], total: 51 });
    if (u.endsWith("/content_group_model")) return jsonResponse({ default_model: model, models: [{ id: model, label: "GPT" }] });
    if (u.endsWith("/save-for-later")) return jsonResponse({ status: "saved_for_later" });
    if (u.endsWith("/content_groups")) return jsonResponse({ content_groups: [{ id: 1, name: "AI", kind: "topic" }] });
    if (u.endsWith("/group-suggestions")) return jsonResponse({ run: init?.method === "POST" ? { status: "queued" } : null, suggestions: [] });
    return jsonResponse({ groups: [], feed_sources: [] });
  });
  render(<MemoryRouter initialEntries={["/feed-review?mode=all"]}><FeedReview /><Location /></MemoryRouter>);
  await screen.findByText("Second");
  expect(screen.getAllByRole("article")).toHaveLength(2);
  expect(screen.getAllByLabelText("Stronicowanie wpisów feedu")).toHaveLength(2);
  expect(screen.queryByLabelText("Nawigacja wpisów")).toBeNull();
  const posts = () => vi.mocked(fetch).mock.calls.filter(([url, init]) => String(url).endsWith("/group-suggestions") && init?.method === "POST");
  await waitFor(() => expect(posts()).toHaveLength(2));
  expect(posts().map(([, init]) => init?.body)).toEqual([JSON.stringify({ model }), JSON.stringify({ model })]);
  const loads = () => vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes("/feed_items?")).length;
  const before = loads();
  fireEvent.click(screen.getAllByText("Do przeczytania")[0]);
  await screen.findByText("Zachowano tylko link do oceny");
  expect(loads()).toBe(before);
  expect(screen.getAllByRole("article")).toHaveLength(2);
  fireEvent.click(screen.getByText("Po jednym wpisie"));
  expect(screen.getByTestId("location").textContent).toContain("mode=single");
  expect(screen.getAllByRole("article")).toHaveLength(1);
  fireEvent.click(screen.getByText("Wszystkie na liście"));
  expect(screen.getByTestId("location").textContent).toContain("mode=all");
  expect(JSON.parse(localStorage.getItem("lenie_feedReviewFilters") || "{}").mode).toBe("all");
  // The remembered "all" choice no longer decides the default: a bare address opens one item at a time.
  cleanup();
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  await screen.findByLabelText("Nawigacja wpisów");
  expect(screen.getAllByRole("article")).toHaveLength(1);
  expect(screen.getByText("Artykuł testowy")).toBeTruthy();
  expect(screen.queryByText("Second")).toBeNull();
});

it("opens one item at a time by default, whatever mode was used last", async () => {
  localStorage.setItem("lenie_feedReviewFilters", JSON.stringify({ feedSourceId: "", view: "new", mode: "all" }));
  render(<MemoryRouter initialEntries={["/feed-review"]}><FeedReview /><Location /></MemoryRouter>);
  await screen.findByLabelText("Nawigacja wpisów");
  expect(screen.getAllByRole("article")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Po jednym wpisie" }).getAttribute("aria-pressed")).toBe("true");
  await waitFor(() => expect(screen.getByTestId("location").textContent).toContain("item=7"));
  expect(screen.getByTestId("location").textContent).not.toContain("mode=all");
});

it("links every entry in the full list to its own single-item view", async () => {
  vi.mocked(fetch).mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/feed_items?")) return jsonResponse({ feed_items: [feedItem, { ...feedItem, id: 8, title: "Second" }], total: 2 });
    if (u.endsWith("/content_group_model")) return jsonResponse({ default_model: "gpt-4o-mini", models: [] });
    return jsonResponse({ groups: [], feed_sources: [], content_groups: [] });
  });
  render(<MemoryRouter initialEntries={["/feed-review?mode=all"]}><FeedReview /><Location /></MemoryRouter>);
  await screen.findByText("Second");
  const links = screen.getAllByText("🔗 Pracuj nad tym wpisem");
  expect(links).toHaveLength(2);
  expect(links[1].getAttribute("href")).toBe("/feed-review?mode=single&item=8");
  fireEvent.click(links[1]);
  await waitFor(() => expect(screen.getByTestId("location").textContent).toContain("item=8"));
  expect(screen.getByTestId("location").textContent).toContain("mode=single");
  expect(screen.getAllByRole("article")).toHaveLength(1);
  expect(screen.getByText("Second")).toBeTruthy();
});

it("shows a copyable link to the displayed item and keeps ?item= in the address", async () => {
  function Location() { return <output data-testid="loc">{useLocation().search}</output>; }
  render(<MemoryRouter initialEntries={["/feed-review"]}><FeedReview /><Location /></MemoryRouter>);
  await screen.findByText("Artykuł testowy");
  const link = (await screen.findByLabelText("Link do tego wpisu:")) as HTMLInputElement;
  expect(link.value).toContain("?item=7");
  await waitFor(() => expect(screen.getByTestId("loc").textContent).toContain("item=7"));
});

it("switches back to Nowe when the remembered tab is the later one", async () => {
  localStorage.setItem("lenie_feedReviewFilters", JSON.stringify({ feedSourceId: "", view: "later", mode: "single" }));
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  const nowe = await screen.findByRole("tab", { name: "Nowe" });
  expect(nowe.getAttribute("aria-selected")).toBe("false");
  fireEvent.click(nowe);
  await waitFor(() => expect(screen.getByRole("tab", { name: "Nowe" }).getAttribute("aria-selected")).toBe("true"));
});

it("opens an item named in the link even when it is outside the loaded list", async () => {
  const outside = { ...feedItem, id: 99, title: "Wpis spoza listy", status: "saved_for_later" };
  const base = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((url, init) => {
    if (String(url).endsWith("/feed_items/99")) return Promise.resolve(jsonResponse(outside));
    return base(url, init);
  });
  render(<MemoryRouter initialEntries={["/feed-review?item=99"]}><FeedReview /></MemoryRouter>);
  expect(await screen.findByText("Wpis spoza listy")).toBeTruthy();
  expect(screen.getByText(/spoza bieżącej listy/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Wróć do listy" }));
  expect(await screen.findByText("Artykuł testowy")).toBeTruthy();
});

it("tells when a saved \"Może kiedyś\" entry expires, only on the later tab", async () => {
  const saved = { ...feedItem, status: "saved_for_later", saved_at: "2026-07-27T10:00:00+00:00", expires_at: "2027-07-27T10:00:00+00:00", retention_months: 12 };
  const base = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((url, init) => {
    if (String(url).includes("/feed_items?")) return Promise.resolve(jsonResponse({ feed_items: [saved], total: 1 }));
    return base(url, init);
  });
  render(<MemoryRouter initialEntries={["/feed-review?view=later"]}><FeedReview /></MemoryRouter>);
  const note = await screen.findByText(/Ważne do:/);
  expect(note.textContent).toContain("(12 mies.)");
  cleanup();
  render(<MemoryRouter initialEntries={["/feed-review?view=new"]}><FeedReview /></MemoryRouter>);
  await screen.findByText("Artykuł testowy");
  expect(screen.queryByText(/Ważne do:/)).toBeNull();
});
