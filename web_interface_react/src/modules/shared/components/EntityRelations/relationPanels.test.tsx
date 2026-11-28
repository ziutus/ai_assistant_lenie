import axios from "axios";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DocumentRelations, RegistryRelations } from "./relationPanels";
vi.mock("axios");
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data: { relations: [], models: [], vocabulary: [] } });
});
const result = { created: 2, evidence_added: 3, skipped_rejected: 1, failed_calls: 1, usage: { llm_cost_amount: null, llm_cost_currency: null }, unresolved: [{ subject: "Nieznany", object: "Firma", quote: "cytat" }] };
it("does not detect automatically; shows running, summary and unresolved, reloads after detection", async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(axios.post).mockImplementation(() => new Promise(r => { resolve = r; }));
  const changed = vi.fn(); render(<DocumentRelations apiUrl="" apiKey="k" documentId={10} onChange={changed} />);
  await screen.findByText("Brak powiązań."); expect(axios.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Zbuduj powiązania"));
  expect((screen.getByText("Zbuduj powiązania") as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/Operacja może potrwać/)).toBeTruthy();
  expect(axios.post).toHaveBeenCalledWith("/document/10/relations/detect", {}, { headers: { "x-api-key": "k" }, timeout: 0 });
  resolve({ data: result }); await screen.findByText(/Nowe: 2/);
  expect(screen.getByText(/Koszt: nieznany/)).toBeTruthy(); expect(screen.getByText(/Nie dopasowano/)).toBeTruthy(); expect(changed).toHaveBeenCalledOnce();
});
it("explains 409 and allows another attempt", async () => {
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 409 } });
  render(<DocumentRelations apiUrl="" apiKey="k" documentId={10} onChange={() => {}} />);
  fireEvent.click(screen.getByText("Zbuduj powiązania"));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Dokument jest zajęty"));
  expect((screen.getByText("Zbuduj powiązania") as HTMLButtonElement).disabled).toBe(false);
});
it("loads the relation model endpoint and saves household selection", async () => {
  vi.mocked(axios.get).mockImplementation(async url => ({ data: String(url).includes("/model") ? { default_model: "m", models: [{ id: "m", label: "Model testowy", available: true }] } : { relations: [] } }));
  vi.mocked(axios.put).mockResolvedValue({ data: { default_model: "m", saved: true } });
  render(<DocumentRelations apiUrl="" apiKey="k" documentId={10} onChange={() => {}} />);
  const details = screen.getByText(/Model powiązań/).closest("details")!;
  details.open = true; fireEvent(details, new Event("toggle"));
  await screen.findByRole("option", { name: /Model testowy/ });
  fireEvent.click(screen.getByText("Ustaw jako domyślny"));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith("/relation_extraction/model", { model: "m" }, expect.anything()));
});
it("offers Wikidata only for linked persons and links unresolved QIDs", async () => {
  const { rerender } = render(<RegistryRelations apiUrl="" apiKey="k" entity={{ type: "person", id: 1 }} />);
  expect(screen.queryByText("Pobierz z Wikidata")).toBeNull();
  rerender(<RegistryRelations apiUrl="" apiKey="k" entity={{ type: "person", id: 1 }} wikidataQid="Q1" />);
  vi.mocked(axios.post).mockResolvedValue({ data: { ...result, unresolved: [{ qid: "Q123", labels: ["Nazwa"] }] } });
  fireEvent.click(screen.getByText("Pobierz z Wikidata"));
  expect(await screen.findByRole("link", { name: "Nazwa (Q123)" })).toHaveProperty("href", "https://www.wikidata.org/wiki/Q123");
});
