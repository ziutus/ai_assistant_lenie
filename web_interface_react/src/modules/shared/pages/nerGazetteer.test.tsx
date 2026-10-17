import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NerGazetteer from "./nerGazetteer";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const entries = [
  { id: 1, kind: "city", name_pl: "Luizjana", patterns: ["luizjan*", "luisian*"], geocode_alias: null,
    note: "transkrypcja", source_document_id: 10872, created_by: "key", created_at: "2026-10-17T20:00:00" },
  { id: 2, kind: "geocode_alias", name_pl: "Kaliningrad", patterns: [], geocode_alias: "Królewiec",
    note: null, source_document_id: null, created_by: null, created_at: null },
];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data: { status: "success", entries } });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.patch).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.delete).mockResolvedValue({ data: { status: "success" } });
});
afterEach(cleanup);

const open = (url = "/ner-gazetteer") => render(
  <MemoryRouter initialEntries={[url]}><Routes><Route path="/ner-gazetteer" element={<NerGazetteer />} /></Routes></MemoryRouter>);

it("lists entries with patterns, alias and a link to the source document", async () => {
  open();
  const table = await screen.findByRole("table");
  expect(within(table).getByText("luizjan*")).toBeTruthy();
  expect(within(table).getByText("Królewiec")).toBeTruthy();
  expect(within(table).getByRole("link", { name: "dok. #10872" }).getAttribute("href")).toBe("/read/10872");
  expect(vi.mocked(axios.get)).toHaveBeenCalledWith("/ner_gazetteer", expect.objectContaining({ params: {} }));
});

it("filters by kind through the URL", async () => {
  open("/ner-gazetteer?kind=city");
  await screen.findByRole("table");
  expect(vi.mocked(axios.get)).toHaveBeenCalledWith("/ner_gazetteer", expect.objectContaining({ params: { kind: "city" } }));
  expect((screen.getByLabelText("Filtr rodzaju") as HTMLSelectElement).value).toBe("city");
});

it("adds a city entry with patterns split by line and comma", async () => {
  open();
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Nazwa polska"), { target: { value: "Teksas" } });
  fireEvent.change(screen.getByLabelText("Wzorce"), { target: { value: "teksas*\ntexas*, teksan*" } });
  fireEvent.change(screen.getByLabelText("Dokument źródłowy"), { target: { value: "10873" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(vi.mocked(axios.post)).toHaveBeenCalled());
  const [url, body, config] = vi.mocked(axios.post).mock.calls[0] as [string, Record<string, unknown>, { headers: Record<string, string> }];
  expect(url).toBe("/ner_gazetteer");
  expect(body).toEqual({ kind: "city", name_pl: "Teksas", note: null, patterns: ["teksas*", "texas*", "teksan*"], source_document_id: 10873 });
  expect(config.headers["x-api-key"]).toBe("test-key");
  expect(await screen.findByRole("status")).toBeTruthy();
});

it("adds a geocoder alias entry without patterns", async () => {
  open();
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Rodzaj wpisu"), { target: { value: "geocode_alias" } });
  fireEvent.change(screen.getByLabelText("Nazwa polska"), { target: { value: "Luizjana" } });
  fireEvent.change(screen.getByLabelText("Alias geokodera"), { target: { value: "Louisiana" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(vi.mocked(axios.post)).toHaveBeenCalled());
  expect(vi.mocked(axios.post).mock.calls[0][1]).toEqual({ kind: "geocode_alias", name_pl: "Luizjana", note: null, geocode_alias: "Louisiana" });
});

it("explains a 403 and shows the backend validation message", async () => {
  vi.mocked(axios.post).mockRejectedValueOnce({ response: { status: 403, data: {} } });
  open();
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Nazwa polska"), { target: { value: "Teksas" } });
  fireEvent.change(screen.getByLabelText("Wzorce"), { target: { value: "te*" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  expect((await screen.findByRole("alert")).textContent).toContain("klucza API typu service");

  vi.mocked(axios.post).mockRejectedValueOnce({ response: { status: 400, data: { message: "Wzorzec za krótki" } } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Wzorzec za krótki"));
});

it("edits patterns and note of an entry", async () => {
  open();
  const table = await screen.findByRole("table");
  fireEvent.click(within(table).getAllByRole("button", { name: "Edytuj" })[0]);
  fireEvent.change(screen.getByLabelText("Wzorce Luizjana"), { target: { value: "luizjan*\nluzjan*" } });
  fireEvent.change(screen.getByLabelText("Notatka Luizjana"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(vi.mocked(axios.patch)).toHaveBeenCalled());
  const [url, body] = vi.mocked(axios.patch).mock.calls[0] as [string, Record<string, unknown>];
  expect(url).toBe("/ner_gazetteer/1");
  expect(body).toEqual({ note: null, patterns: ["luizjan*", "luzjan*"] });
});

it("deletes only after a second confirming click", async () => {
  open();
  const table = await screen.findByRole("table");
  fireEvent.click(within(table).getAllByRole("button", { name: "Usuń" })[1]);
  expect(vi.mocked(axios.delete)).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Potwierdź usunięcie" }));
  await waitFor(() => expect(vi.mocked(axios.delete)).toHaveBeenCalledWith("/ner_gazetteer/2", expect.anything()));
});

it("shows an empty-state message when the database has no entries", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { status: "success", entries: [] } });
  open();
  expect(await screen.findByText(/Brak wpisów w bazie/)).toBeTruthy();
});
