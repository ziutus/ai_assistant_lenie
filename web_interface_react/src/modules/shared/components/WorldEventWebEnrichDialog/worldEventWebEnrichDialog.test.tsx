import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import WorldEventWebEnrichDialog from "./worldEventWebEnrichDialog";
import type { WorldEvent } from "../WorldEventCard/worldEventCard";

vi.mock("axios");
const event: WorldEvent = {
  id: 1, title: "Wybory", description: "Stary opis", kind: "other", event_date: null, date_precision: "unknown",
  event_date_end: null, end_date_precision: null, is_ongoing: false, status: "confirmed", version: 4, aliases: [], participants: [],
};
const result = {
  source_step: "wikipedia", wikipedia: { found: true, lang: "pl", title: "Wybory", url: "https://pl.wikipedia.org/wiki/Wybory" },
  proposal: { description: "Nowy opis", kind: "election", event_date: "2026-01-01", event_date_end: null,
    is_ongoing: false, countries: ["polska"], organizations: ["WHO"], sources_used: [{ url: "https://example.org/event", quote: "Wybory" }] },
  sources: [{ title: "Źródło", url: "https://example.org/event", snippet: "Wybory w Polsce" }], rejected: {}, model: "test",
  usage: { serper_credits: 0, firecrawl_credits: 0, llm: { llm_cost_amount: "0.004", llm_cost_currency: "USD" } },
};
const open = () => render(<WorldEventWebEnrichDialog event={event} kinds={[{ code: "election", label: "Wybory" }]}
  apiUrl="" headers={{ "x-api-key": "test" }} onClose={vi.fn()} onChanged={vi.fn()} />);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("/model")
    ? { default_model: "test", saved: false, models: [{ id: "test", label: "Test", available: true }] }
    : { serper: { credits_left: null, error: "Brak" }, firecrawl: { remaining: 80, plan: 100 } } }));
  vi.mocked(axios.post).mockImplementation(async (url, body) => ({ data: url.endsWith("/estimate")
    ? { serper_credits: (body as { step: string }).step === "web" ? 1 : 0, firecrawl_credits: (body as { step: string }).step === "web" ? 2 : 0, llm: { model: "test", est_cost_usd: "0.003" } } : result }));
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
});
afterEach(cleanup);

it("shows the estimate and tolerates one unavailable credit provider without running research", async () => {
  open();
  expect((await screen.findByText(/Szacunek:/)).textContent).toContain("LLM ≈ $0,003");
  expect(screen.getByText(/Pozostało:/).textContent).toContain("Serper niedostępne · Firecrawl 80");
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(axios.patch).not.toHaveBeenCalled();
});

it("applies only checked fields and participants with the loaded version", async () => {
  open();
  await screen.findByText(/Szacunek:/);
  fireEvent.click(screen.getByRole("button", { name: "Szukaj w Wikipedii" }));
  await screen.findByRole("group", { name: "Proponowane zmiany" });
  expect(axios.patch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox", { name: /^Rodzaj:/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: /^Kraj:/ }));
  fireEvent.click(screen.getByRole("button", { name: "Zastosuj zaznaczone" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/geo_events/1", { kind: "election", expected_version: 4 }, { headers: { "x-api-key": "test" } }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/geo_events/1/participants", { type: "country", ref: "polska", role: "subject" }, { headers: { "x-api-key": "test" } }));
  expect(axios.get).toHaveBeenCalledTimes(3);
  expect(screen.getByText(/Zużycie:/).textContent).toContain("$0,004");
});

it("includes source URLs only when the description is approved", async () => {
  open();
  await screen.findByText(/Szacunek:/);
  fireEvent.click(screen.getByRole("button", { name: "Szukaj w Wikipedii" }));
  await screen.findByRole("group", { name: "Proponowane zmiany" });
  fireEvent.click(screen.getByRole("checkbox", { name: /^Opis:/ }));
  fireEvent.click(screen.getByRole("button", { name: "Zastosuj zaznaczone" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/geo_events/1",
    { description: "Nowy opis\n\nŹródła:\nhttps://example.org/event", expected_version: 4 }, { headers: { "x-api-key": "test" } }));
});

it("can approve an organization without patching unchecked event fields", async () => {
  open();
  await screen.findByText(/Szacunek:/);
  fireEvent.click(screen.getByRole("button", { name: "Szukaj w Wikipedii" }));
  await screen.findByRole("group", { name: "Proponowane zmiany" });
  fireEvent.click(screen.getByRole("checkbox", { name: /^Organizacja:/ }));
  fireEvent.click(screen.getByRole("button", { name: "Zastosuj zaznaczone" }));
  await screen.findByText("Zastosowano zaznaczone zmiany.");
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.post).toHaveBeenCalledWith("/geo_events/1/participants", { type: "organization", ref: "WHO", role: "subject" }, { headers: { "x-api-key": "test" } });
});

it("shows request diagnostics on a failed search", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  open();
  await screen.findByText(/Szacunek:/);
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 503, data: { message: "Brak klucza" } }, config: { method: "post", url: "/geo_events/1/web_enrich" } });
  fireEvent.click(screen.getByRole("button", { name: "Szukaj w Wikipedii" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Brak klucza");
  expect(screen.getByRole("alert").textContent).toContain("/geo_events/1/web_enrich");
  vi.restoreAllMocks();
});

it("starts with Wikipedia and reveals the paid estimate only after explicit web selection", async () => {
  open();
  expect((await screen.findByText(/Szacunek:/)).textContent).toContain("Wikipedia: 0 kredytów");
  expect(screen.queryByText("Liczba stron do pobrania")).toBeNull();
  expect(axios.post).toHaveBeenCalledWith("/geo_events/1/web_enrich/estimate",
    { model: "test", scrape_pages: 2, step: "wikipedia", with_wikipedia: false }, expect.anything());
  fireEvent.click(screen.getByRole("button", { name: "Szukaj w Wikipedii" }));
  await screen.findByRole("link", { name: "pl: Wybory" });
  expect(axios.post).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "Szukaj dalej w internecie (Serper + Firecrawl)" }));
  expect((await screen.findByText(/Szacunek:/)).textContent).toContain("Serper: 1 kredyt · Firecrawl: 2 kredytów");
  fireEvent.click(screen.getByRole("checkbox", { name: "Użyj artykułu z Wikipedii jako kontekstu" }));
  fireEvent.click(screen.getByRole("button", { name: "Szukaj w internecie" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/geo_events/1/web_enrich",
    { model: "test", scrape_pages: 2, step: "web", with_wikipedia: true }, expect.anything()));
});

it("offers web search after a Wikipedia miss without automatically spending credits", async () => {
  open();
  await screen.findByText(/Szacunek:/);
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { ...result, proposal: null, sources: [],
    wikipedia: { found: false, lang: null, title: null, url: null }, suggest_web: true } });
  fireEvent.click(screen.getByRole("button", { name: "Szukaj w Wikipedii" }));
  await screen.findByText(/Nie znaleziono artykułu/);
  expect(screen.getByRole("button", { name: "Szukaj dalej w internecie (Serper + Firecrawl)" })).toBeTruthy();
  expect(axios.post).toHaveBeenCalledTimes(2);
  expect(screen.getByText(/Szacunek:/).textContent).toContain("Wikipedia: 0 kredytów");
});
