import axios from "axios";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import EntityRelations from "./entityRelations";
import type { Relation } from "./types";
vi.mock("axios");
afterEach(cleanup);
const row: Relation = { id: 1, subject: { type: "person", id: 1, name: "Ada" }, object: { type: "organization", id: 2, name: "Firma" }, other: { type: "organization", id: 2, name: "Firma" }, direction: "outgoing", relation: "pracownik", label: "pracuje w", title: null, valid_from: null, valid_to: null, status: "proposed", detection_method: "llm", source: "entity_relations", editable: true, evidence: [{ id: 1, document_id: null, document_title: null, quote: "<img> cytat", claim: "zaprzeczenie", source_url: "javascript:alert(1)" }] };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async url => ({ data: String(url).includes("vocabulary") ? { vocabulary: [] } : { relations: [row] } }));
  vi.mocked(axios.patch).mockResolvedValue({ data: {} }); vi.mocked(axios.delete).mockResolvedValue({ data: {} });
});
const show = () => render(<EntityRelations apiUrl="" apiKey="k" path="/document/10/relations" />);
it("confirms, rejects, edits and reloads with authentication", async () => {
  show(); await screen.findByText("Propozycje");
  fireEvent.click(screen.getByText("Zatwierdź"));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/entity_relations/1", { status: "confirmed" }, { headers: { "x-api-key": "k" } }));
  await screen.findByText("Odrzuć"); fireEvent.click(screen.getByText("Odrzuć"));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/entity_relations/1", { status: "rejected" }, expect.anything()));
  await screen.findByText("Edytuj"); fireEvent.click(screen.getByText("Edytuj"));
  fireEvent.change(screen.getByLabelText("Tytuł"), { target: { value: "Minister" } }); fireEvent.click(screen.getByText("Zapisz"));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/entity_relations/1", { title: "Minister", valid_from: null, valid_to: null }, expect.anything()));
});
it("requires inline confirmation to delete and hides unsafe evidence links", async () => {
  show(); await screen.findByText("zaprzeczenie");
  expect(screen.queryByText("Źródło ↗")).toBeNull(); expect(screen.getByText("<img> cytat").querySelector("img")).toBeNull();
  fireEvent.click(screen.getByText("Usuń")); expect(axios.delete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Anuluj usunięcie")); expect(axios.delete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Usuń")); fireEvent.click(screen.getByText("Potwierdź usunięcie"));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/entity_relations/1", expect.anything()));
});
it("requests rejected rows only when enabled; legacy rows have no actions", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { relations: [{ ...row, editable: false, status: "confirmed", source: "person_territories" }] } });
  show(); await screen.findByText("z danych organizacji/osoby"); expect(screen.queryByText("Usuń")).toBeNull();
  fireEvent.click(screen.getByLabelText("Pokaż odrzucone"));
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/document/10/relations", { headers: { "x-api-key": "k" }, params: { include_rejected: 1 } }));
});
it("shows request failures and allows retry", async () => {
  vi.mocked(axios.get).mockRejectedValue(new Error("Awaria")); show(); await screen.findByRole("alert");
  vi.mocked(axios.get).mockResolvedValue({ data: { relations: [] } }); fireEvent.click(screen.getByText("Spróbuj ponownie"));
  await screen.findByText("Brak powiązań.");
});
