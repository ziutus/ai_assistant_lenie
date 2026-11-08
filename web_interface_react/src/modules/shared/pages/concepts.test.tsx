import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Concepts from "./concepts";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

beforeEach(() => vi.resetAllMocks());
afterEach(() => cleanup());

const concept = {
  id: 5, name: "Ciemne oświecenie", description: "Nurt myśli politycznej.", document_count: 1,
  aliases: [{ id: 1, alias: "Ciemne oświecenie" }, { id: 2, alias: "Dark Enlightenment" }],
  documents: [{ id: 11239, title: "Wykład", surfaces: ["Ciemne oświecenie"] }],
};

it("lists concepts with description, names and documents", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 1, concepts: [concept] } });
  render(<MemoryRouter initialEntries={["/concepts?q=ciemne"]}><Concepts /></MemoryRouter>);
  const list = await screen.findByRole("list", { name: "Pojęcia" });
  const [first] = within(list).getAllByRole("listitem");
  expect(first.textContent).toContain("Nurt myśli politycznej.");
  expect(first.textContent).toContain("Dark Enlightenment");
  expect(within(first).getByRole("link", { name: "Wykład" }).getAttribute("href")).toBe("/read/11239");
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/concepts", {
    headers: { "x-api-key": "test-key" }, params: { q: "ciemne", limit: 50, offset: 0 } }));
});

it("opens one concept by id", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { concept } });
  render(<MemoryRouter initialEntries={["/concepts?id=5"]}><Concepts /></MemoryRouter>);
  expect(await screen.findByText(/Nurt myśli politycznej/)).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith("/concepts/5", { headers: { "x-api-key": "test-key" } });
});

it("saves an edited description", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 1, concepts: [concept] } });
  vi.mocked(axios.patch).mockResolvedValue({ data: { status: "success" } });
  render(<MemoryRouter><Concepts /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "Edytuj" }));
  fireEvent.change(screen.getByLabelText("Opis"), { target: { value: "Nowy opis" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/concepts/5",
    { name: "Ciemne oświecenie", description: "Nowy opis" }, { headers: { "x-api-key": "test-key" } }));
});

it("links an unlinked name to a suggested concept", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 1, mentions: [{
    name: "Ciemnego oświecenia", name_key: "ciemnego oświecenia", mentions: 2, document_count: 1,
    documents: [{ id: 11239, title: "Wykład", mentions: 2 }],
    suggestions: [{ reason: "similar", score: 0.7, concept: { id: 5, name: "Ciemne oświecenie", description: null } }],
  }] } });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  render(<MemoryRouter initialEntries={["/concepts?tab=unlinked"]}><Concepts /></MemoryRouter>);
  expect(await screen.findByText(/Czy to „Ciemne oświecenie”/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Tak, powiąż" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/concepts/mentions/link",
    { name: "Ciemnego oświecenia", concept_id: 5 }, { headers: { "x-api-key": "test-key" } }));
});

it("explains an empty registry", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 0, concepts: [] } });
  render(<MemoryRouter><Concepts /></MemoryRouter>);
  expect(await screen.findByText("Brak pojęć.")).toBeTruthy();
});
