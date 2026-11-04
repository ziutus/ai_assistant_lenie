import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import WorldEvents from "./worldEvents";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const KINDS = [
  { code: "election", label: "Wybory" }, { code: "outage", label: "Awaria / incydent techniczny" }, { code: "other", label: "Inne" },
];
const ROLES = [
  { code: "actor", label: "sprawca" }, { code: "location", label: "miejsce" }, { code: "subject", label: "podmiot" },
];
const ISRAEL = { id: 3, slug: "izrael", name_pl: "Izrael" };

const election = {
  id: 1, title: "Wybory do Knesetu 2026", description: "Przedterminowe wybory.", kind: "election",
  event_date: "2026-11-03", date_precision: "day", event_date_end: null, end_date_precision: null, is_ongoing: false,
  status: "confirmed", version: 4, aliases: [{ id: 10, alias: "Wybory do Knesetu 2026" }, { id: 11, alias: "Wybory w Izraelu" }],
  participants: [
    { type: "country", role: "location", country: ISRAEL },
    { type: "person", role: "subject", person: { id: 7, name: "Benjamin Netanjahu" } },
  ],
  document_count: 2, source_count: 1, mention_names: ["Wybory w Izraelu"],
  documents: [{ id: 11205, title: "Artykuł o wyborach", via: "source" }, { id: 7, title: null, via: "mention" }],
};
const outage = {
  id: 2, title: "Awaria CrowdStrike", description: null, kind: "outage", event_date: null, date_precision: "unknown",
  event_date_end: null, end_date_precision: null, is_ongoing: false, status: "proposed", version: 1,
  aliases: [{ id: 20, alias: "Awaria CrowdStrike" }], participants: [], document_count: 0, source_count: 0, mention_names: [], documents: [],
};
const mention = {
  name_key: "wybory w polsce", name: "Wybory w Polsce", description: null, mentions: 3, document_count: 2,
  documents: [{ id: 5, title: "Dokument o Polsce", mentions: 2, entity_id: 50 }, { id: 6, title: null, mentions: 1, entity_id: 60 }],
  suggestions: [{ reason: "alias", score: 1, event: { id: 9, title: "Wybory parlamentarne w Polsce 2023", kind: "election", event_date: "2023-10-15", status: "confirmed" } }],
};

const respond = (overrides: Record<string, unknown> = {}) => {
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url in overrides) return { data: overrides[url] };
    if (url.endsWith("/geo_event_kinds")) return { data: { kinds: KINDS } };
    if (url.endsWith("/geo_event_roles")) return { data: { roles: ROLES } };
    if (url.endsWith("/countries")) return { data: { countries: [ISRAEL] } };
    if (url.endsWith("/world_events/unlinked")) return { data: { total: 1, mentions: [mention] } };
    if (url.endsWith("/world_events")) return { data: { total: 2, events: [election, outage] } };
    return { data: {} };
  });
};

const open = (path = "/world-events") =>
  render(<MemoryRouter initialEntries={[path]}><WorldEvents /></MemoryRouter>);
const H = { headers: { "x-api-key": "test-key" } };

beforeEach(() => { vi.resetAllMocks(); respond(); });
afterEach(() => cleanup());

it("lists registry events with kind, dates, participants of every kind, names and documents", async () => {
  open();
  const list = await screen.findByRole("list", { name: "Zdarzenia" });
  const [first, second] = list.children as unknown as HTMLElement[];
  expect(first.textContent).toContain("Wybory do Knesetu 2026");
  expect(first.textContent).toContain("Wybory · 2026-11-03 · zatwierdzone");
  expect(first.textContent).toContain("Izrael (miejsce)");
  expect(first.textContent).toContain("Benjamin Netanjahu (podmiot)");
  expect(within(first).getByLabelText("Nazwy").textContent).toContain("Wybory w Izraelu");
  expect(within(first).getByRole("link", { name: "Artykuł o wyborach" }).getAttribute("href")).toBe("/read/11205");
  expect(within(first).getByRole("link", { name: /Dokument 7/ }).textContent).toContain("⟲");
  expect(second.textContent).toContain("Awaria / incydent techniczny · bez daty · propozycja");
  expect(second.textContent).toContain("Bez uczestników (kraj nie jest wymagany).");
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/world_events", { ...H, params: { limit: 25, offset: 0 } }));
});

it("passes the search, kind and country filters to the registry", async () => {
  open("/world-events?q=wybory&kind=election&with_countries=0");
  await screen.findByRole("list", { name: "Zdarzenia" });
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/world_events", {
    ...H, params: { q: "wybory", kind: "election", with_countries: "0", limit: 25, offset: 0 } }));
  expect((screen.getByLabelText("Rodzaj zdarzenia") as HTMLSelectElement).value).toBe("election");
});

it("filters by country and by status and keeps both in the URL", async () => {
  open("/world-events?country=izrael&status=proposed");
  await screen.findByRole("list", { name: "Zdarzenia" });
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/world_events", {
    ...H, params: { country: "izrael", status: "proposed", limit: 25, offset: 0 } }));
  expect((screen.getByLabelText("Kraj") as HTMLSelectElement).value).toBe("izrael");
  expect((screen.getByLabelText("Status zdarzenia") as HTMLSelectElement).value).toBe("proposed");
  fireEvent.change(screen.getByLabelText("Status zdarzenia"), { target: { value: "confirmed" } });
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/world_events", {
    ...H, params: { country: "izrael", status: "confirmed", limit: 25, offset: 0 } }));
});

it("explains an empty registry and an error", async () => {
  respond({ "/world_events": { total: 0, events: [] } });
  open();
  expect(await screen.findByText("Brak zdarzeń.")).toBeTruthy();
  cleanup();
  vi.mocked(axios.get).mockRejectedValue({ response: { status: 500, data: { message: "Błąd serwera (OperationalError)" } } });
  open();
  expect((await screen.findByRole("alert")).textContent).toContain("Błąd serwera (OperationalError)");
});

it("adds an event without a country", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { created: true, event: outage } });
  open();
  await screen.findByRole("list", { name: "Zdarzenia" });
  fireEvent.change(screen.getByLabelText("Nazwa nowego zdarzenia"), { target: { value: "Halving Bitcoina" } });
  fireEvent.change(screen.getByLabelText("Rodzaj nowego zdarzenia"), { target: { value: "other" } });
  fireEvent.change(screen.getByLabelText("Inne nazwy nowego zdarzenia"), { target: { value: "Bitcoin halving, halving BTC" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/geo_events", {
    title: "Halving Bitcoina", kind: "other", is_ongoing: false, status: "confirmed", aliases: ["Bitcoin halving", "halving BTC"],
    description: undefined, event_date: undefined, event_date_end: undefined }, H));
  expect((await screen.findByRole("status")).textContent).toContain("Dodano zdarzenie.");
  fireEvent.change(screen.getByLabelText("Nazwa nowego zdarzenia"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Podaj nazwę zdarzenia.");
});

it("edits only the changed fields and sends the version it loaded", async () => {
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
  open();
  const list = await screen.findByRole("list", { name: "Zdarzenia" });
  const card = list.children[1] as HTMLElement;
  fireEvent.click(within(card).getByRole("button", { name: "Edytuj" }));
  fireEvent.change(within(card).getByLabelText("Data początku"), { target: { value: "2024-07-19" } });
  fireEvent.change(within(card).getByLabelText("Opis zdarzenia"), { target: { value: "Globalna awaria Windows." } });
  fireEvent.click(within(card).getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/geo_events/2",
    { event_date: "2024-07-19", description: "Globalna awaria Windows.", expected_version: 1 }, H));
});

it("tells the reader when somebody else changed the event meanwhile", async () => {
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { message: "The event changed since you loaded it; reload" } } });
  open();
  const card = (await screen.findByRole("list", { name: "Zdarzenia" })).children[0] as HTMLElement;
  fireEvent.click(within(card).getByRole("button", { name: "Edytuj" }));
  fireEvent.change(within(card).getByLabelText("Nazwa zdarzenia"), { target: { value: "Inna nazwa" } });
  fireEvent.click(within(card).getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Ktoś zmienił to zdarzenie w międzyczasie");
});

it("adds an organization by name and removes a participant", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  vi.mocked(axios.delete).mockResolvedValue({ data: {} });
  open();
  const card = (await screen.findByRole("list", { name: "Zdarzenia" })).children[1] as HTMLElement;
  fireEvent.click(within(card).getByRole("button", { name: "Edytuj" }));
  fireEvent.change(within(card).getByLabelText("Typ uczestnika"), { target: { value: "organization" } });
  fireEvent.change(within(card).getByLabelText("Uczestnik (id lub dokładna nazwa)"), { target: { value: "CrowdStrike" } });
  fireEvent.change(within(card).getByLabelText("Rola uczestnika"), { target: { value: "actor" } });
  fireEvent.click(within(card).getByRole("button", { name: "Dodaj uczestnika" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/geo_events/2/participants",
    { type: "organization", ref: "CrowdStrike", role: "actor" }, H));

  const first = (await screen.findByRole("list", { name: "Zdarzenia" })).children[0] as HTMLElement;
  fireEvent.click(within(first).getByRole("button", { name: "Usuń uczestnika Benjamin Netanjahu" }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/geo_events/1/participants",
    { ...H, data: { type: "person", id: 7, role: "subject" } }));
});

it("shows named mentions with suggestions and links one on confirmation", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  open("/world-events?tab=unlinked");
  const item = (await screen.findByRole("list", { name: "Nazwy do powiązania" })).children[0] as HTMLElement;
  expect(item.textContent).toContain("Wybory w Polsce");
  expect(within(item).getByRole("link", { name: "Dokument o Polsce ×2" }).getAttribute("href")).toBe("/ner/5");
  expect(within(item).getByLabelText("Podpowiedzi").textContent).toContain("Wybory parlamentarne w Polsce 2023 (2023-10-15)");
  expect(within(item).getByLabelText("Podpowiedzi").textContent).toContain("ta sama nazwa");
  expect(axios.post).not.toHaveBeenCalled(); // a name alone links nothing
  fireEvent.click(within(item).getByRole("button", { name: "Tak, powiąż" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/world_events/mentions/link", { name: "Wybory w Polsce", event_id: 9 }, H));
  expect((await screen.findByRole("status")).textContent).toContain("Powiązano „Wybory w Polsce”");
});

it("remembers a refused suggestion, creates an event from a mention and links to a numbered one", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  open("/world-events?tab=unlinked");
  const item = (await screen.findByRole("list", { name: "Nazwy do powiązania" })).children[0] as HTMLElement;
  fireEvent.click(within(item).getByRole("button", { name: "To nie to" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/world_events/mentions/reject", { name: "Wybory w Polsce", event_id: 9 }, H));

  fireEvent.change(within(item).getByLabelText("Rodzaj dla Wybory w Polsce"), { target: { value: "election" } });
  fireEvent.click(within(item).getByRole("button", { name: "Utwórz zdarzenie" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/world_events/from_mention", { name: "Wybory w Polsce", kind: "election" }, H));

  const link = within(item).getByRole("button", { name: "Powiąż z istniejącym" }) as HTMLButtonElement;
  expect(link.disabled).toBe(true);
  fireEvent.change(within(item).getByLabelText("Numer zdarzenia dla Wybory w Polsce"), { target: { value: "42" } });
  expect(link.disabled).toBe(false);
  fireEvent.click(link);
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/world_events/mentions/link", { name: "Wybory w Polsce", event_id: 42 }, H));
});

it("says when every mention is linked, and reports a failed decision", async () => {
  respond({ "/world_events/unlinked": { total: 0, mentions: [] } });
  open("/world-events?tab=unlinked");
  expect(await screen.findByText("Wszystkie nazwy są powiązane.")).toBeTruthy();
  cleanup();
  respond();
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 404, data: { message: "Event not found" } } });
  open("/world-events?tab=unlinked");
  const item = (await screen.findByRole("list", { name: "Nazwy do powiązania" })).children[0] as HTMLElement;
  fireEvent.click(within(item).getByRole("button", { name: "Tak, powiąż" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Event not found");
});
