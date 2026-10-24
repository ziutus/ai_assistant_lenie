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
};

function jsonResponse(body: object) {
  return new Response(JSON.stringify(body), { status: 200 });
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn((url: string) => {
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
  cleanup();
  render(<MemoryRouter><FeedReview /></MemoryRouter>);
  await screen.findByText("Second");
  expect(screen.getAllByRole("article")).toHaveLength(2);
});

it("shows a copyable link to the displayed item and keeps ?item= in the address", async () => {
  function Location() { return <output data-testid="loc">{useLocation().search}</output>; }
  render(<MemoryRouter initialEntries={["/feed-review"]}><FeedReview /><Location /></MemoryRouter>);
  await screen.findByText("Artykuł testowy");
  const link = (await screen.findByLabelText("Link do tego wpisu:")) as HTMLInputElement;
  expect(link.value).toContain("?item=7");
  await waitFor(() => expect(screen.getByTestId("loc").textContent).toContain("item=7"));
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
