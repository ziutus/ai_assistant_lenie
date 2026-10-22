import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import FeedReview from "./feedReview";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas:5000", apiKey: "test-key" }) };
});
vi.mock("../components/ContentGroupsPanel/ContentGroupsPanel", () => ({ default: () => null }));

const feedItem = {
  id: 7, feed_source_id: 1, title: "Artykuł testowy", url: "https://example.com/a", summary: null,
  published_at: null, status: "new", saved_at: null, saved_by_user_id: null,
};

function jsonResponse(body: object) {
  return new Response(JSON.stringify(body), { status: 200 });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url.includes("/feed_items?")) return Promise.resolve(jsonResponse({ feed_items: [feedItem], total: 1 }));
    if (url.endsWith("/feed_sources")) return Promise.resolve(jsonResponse({ feed_sources: [{ id: 1, name: "Blog", type: "rss", disabled: false }] }));
    if (url.endsWith("/content_groups")) return Promise.resolve(jsonResponse({ content_groups: [] }));
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
