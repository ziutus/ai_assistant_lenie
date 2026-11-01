import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Geopolitics from "./geopolitics";

vi.mock("axios");
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: any) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  GeoJSON: () => null,
}));
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const MODELS = [
  { id: "bielik", label: "Bielik 11B", available: true, input_price_per_million: "0.2", output_price_per_million: "0.4", currency: "USD" },
  { id: "openrouter/x/y", label: "Mistral Small", available: true, input_price_per_million: "0.1", output_price_per_million: "0.3", currency: "USD" },
  { id: "vertex/z", label: "Gemini", available: false, unavailable_reason: "brak poświadczeń", currency: "USD" },
];
const BRA = { id: 1, slug: "brazylia", name_pl: "Brazylia", map_code: "BRA", iso3: "BRA" };
const USA = { id: 2, slug: "stany-zjednoczone", name_pl: "Stany Zjednoczone", map_code: "USA", iso3: "USA" };
const event = {
  id: 9, title: "Opozycjonista uciekł do USA", description: null, event_date: "2026-03-10", status: "proposed",
  detection_method: "llm", model: "m", participants: [{ country: BRA, role: "actor" }, { country: USA, role: "target" }],
  sources: [{ id: 1, document_id: 77, quote: "uciekł do USA", stance: "supports" }],
};
const assessment = {
  id: 5, from_country: BRA, to_country: USA, axis: "political", score: -1, confidence: 0.4, valid_from: "2026-03-10",
  valid_to: null, review_due_at: null, overdue: false, rationale: "Hipoteza.", status: "proposed",
  detection_method: "llm", version: 1, evidence: [{ event, stance: "supports" }],
  current: { ...{ id: 4, from_country: BRA, to_country: USA, axis: "political", score: 1, confidence: 0.8, valid_from: "2025-01-01",
    valid_to: null, review_due_at: null, overdue: false, rationale: null, status: "confirmed", detection_method: "manual", version: 2 } },
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: async () => ({ type: "FeatureCollection", features: [] }) }));
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/countries")) return { data: { countries: [BRA, USA] } };
    if (url.endsWith("/geopolitics/axes")) return { data: { axes: [{ value: "political", label: "Polityczna", scale: { "-1": "napięta" } }] } };
    if (url.endsWith("/geopolitics/model")) return { data: { default_model: "bielik", saved: false, models: MODELS } };
    if (url.endsWith("/geopolitics/proposals")) return { data: { proposals: [assessment] } };
    if (url.endsWith("/country_relations")) return { data: { relations: [{ ...assessment, status: "confirmed", other_country: USA }] } };
    if (url.endsWith("/geo_events")) return { data: { total: 1, events: [event] } };
    return { data: {} };
  });
});
afterEach(() => cleanup());

it("shows the proposal next to the assessment it would replace and sends the expected version on approval", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  render(<MemoryRouter initialEntries={["/geopolitics?tab=proposals"]}><Geopolitics /></MemoryRouter>);
  const list = await screen.findByRole("list", { name: "Propozycje" });
  const item = list.children[0] as HTMLElement;
  expect(item.textContent).toContain("Brazylia → Stany Zjednoczone");
  expect(item.textContent).toContain("napięta (-1)");
  expect(item.textContent).toContain("obecnie: przyjazna (+1) od 2025-01-01");
  expect(item.textContent).toContain("zaproponował model");
  expect(within(item).getByRole("link", { name: "Dokument 77" }).getAttribute("href")).toBe("/read/77");

  fireEvent.click(within(item).getByRole("button", { name: "Zatwierdź zdarzenie i zmianę" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    "/geopolitics/proposals/5/decision", { decision: "approve", expected_version: 1 }, { headers: { "x-api-key": "test-key" } },
  ));
  expect((await screen.findByRole("status")).textContent).toContain("Poprzedni okres relacji został zamknięty");
});

it("lists confirmed relations of the selected country and says no data is not neutral", async () => {
  render(<MemoryRouter initialEntries={["/geopolitics?country=brazylia&at=2026-06-01"]}><Geopolitics /></MemoryRouter>);
  const list = await screen.findByRole("list", { name: "Relacje" });
  expect(list.children[0].textContent).toContain("Brazylia → Stany Zjednoczone");
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/country_relations", {
    headers: { "x-api-key": "test-key" }, params: { country: "brazylia", at: "2026-06-01", axis: "political", direction: "from" },
  }));
});

it("tells the reader that an empty result is missing data", async () => {
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/countries")) return { data: { countries: [BRA, USA] } };
    if (url.endsWith("/country_relations")) return { data: { relations: [] } };
    return { data: {} };
  });
  render(<MemoryRouter initialEntries={["/geopolitics?country=brazylia"]}><Geopolitics /></MemoryRouter>);
  expect((await screen.findByText(/To brak danych, nie neutralność/)).textContent).toContain("Brazylia");
});

it("shows an error when a decision conflicts", async () => {
  vi.mocked(axios.post).mockRejectedValue({ response: { data: { message: "The assessment changed since you loaded it; reload" } } });
  render(<MemoryRouter initialEntries={["/geopolitics?tab=proposals"]}><Geopolitics /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "Odrzuć" }));
  expect((await screen.findByRole("alert")).textContent).toContain("The assessment changed");
});

it("lists events with participants and lets a proposed one be confirmed", async () => {
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
  render(<MemoryRouter initialEntries={["/geopolitics?tab=events"]}><Geopolitics /></MemoryRouter>);
  const list = await screen.findByRole("list", { name: "Zdarzenia" });
  expect(list.textContent).toContain("Brazylia (sprawca), Stany Zjednoczone (cel)");
  fireEvent.click(within(list).getByRole("button", { name: "Zatwierdź zdarzenie" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/geo_events/9", { status: "confirmed" }, { headers: { "x-api-key": "test-key" } }));
});


it("offers models with prices, greys out unavailable ones and sends the chosen model with the analysis", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: {
    events_created: 2, events_existing: 0, assessments_proposed: 1, assessments_merged: 0, dated_from_reference: 0,
    rejected: {}, model: "openrouter/x/y", usage: { llm_cost_amount: "0.0042", llm_cost_currency: "USD", llm_cost_status: "estimated", llm_tokens: 1234 },
  } });
  render(<MemoryRouter initialEntries={["/geopolitics"]}><Geopolitics /></MemoryRouter>);
  const select = await screen.findByRole("combobox", { name: "Model do analizy" });
  await waitFor(() => expect((select as HTMLSelectElement).value).toBe("bielik"));
  const options = within(select).getAllByRole("option");
  expect(options[0].textContent).toContain("$0.2 / $0.4 za 1 mln tok.");
  expect(options[0].textContent).toContain("domyślny");
  expect((options[2] as HTMLOptionElement).disabled).toBe(true);
  expect(options[2].textContent).toContain("niedostępny: brak poświadczeń");

  fireEvent.change(select, { target: { value: "openrouter/x/y" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Numer dokumentu" }), { target: { value: "11205" } });
  fireEvent.click(screen.getByRole("button", { name: "Zaproponuj zdarzenia" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    "/document/11205/geopolitics/detect", { model: "openrouter/x/y" }, { headers: { "x-api-key": "test-key" }, timeout: 180000 },
  ));
  const notice = (await screen.findByRole("status")).textContent ?? "";
  expect(notice).toContain("Koszt: 0.0042 USD (szacunek)");
  expect(notice).toContain("model openrouter/x/y");
});

it("saves the chosen model as the household default", async () => {
  vi.mocked(axios.put).mockResolvedValue({ data: { default_model: "openrouter/x/y", saved: true } });
  render(<MemoryRouter initialEntries={["/geopolitics"]}><Geopolitics /></MemoryRouter>);
  const select = await screen.findByRole("combobox", { name: "Model do analizy" });
  await waitFor(() => expect((select as HTMLSelectElement).value).toBe("bielik"));
  fireEvent.change(select, { target: { value: "openrouter/x/y" } });
  fireEvent.click(screen.getByRole("button", { name: "Ustaw jako domyślny" }));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith("/geopolitics/model", { model: "openrouter/x/y" }, { headers: { "x-api-key": "test-key" } }));
  expect((await screen.findByRole("status")).textContent).toContain("Zapisano domyślny model");
  expect(screen.getByRole("button", { name: "Przywróć domyślny serwera" })).toBeTruthy();
});
