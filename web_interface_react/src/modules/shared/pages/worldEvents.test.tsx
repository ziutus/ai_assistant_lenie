import axios from "axios";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import WorldEvents from "./worldEvents";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

beforeEach(() => vi.resetAllMocks());
afterEach(() => cleanup());

it("lists events with their description and links to the NER page of each document", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 2, events: [
    { name: "Galanbard 2026", description: "Wspólne ćwiczenia wojskowe.", mentions: 3, document_count: 1,
      documents: [{ id: 10872, title: "Film o Bałtyku", mentions: 3, entity_id: 5 }] },
    { name: "Szczyt w Hadze", description: null, mentions: 1, document_count: 1,
      documents: [{ id: 7, title: null, mentions: 1, entity_id: 6 }] },
  ] } });
  render(<MemoryRouter initialEntries={["/world-events?q=gal"]}><WorldEvents /></MemoryRouter>);
  const list = await screen.findByRole("list", { name: "Wydarzenia" });
  const [first, second] = within(list).getAllByRole("listitem");
  expect(first.textContent).toContain("Wspólne ćwiczenia wojskowe.");
  expect(within(first).getByRole("link", { name: /Film o Bałtyku/ }).getAttribute("href")).toBe("/ner/10872");
  expect(second.textContent).toContain("Brak opisu");
  expect(within(second).getByRole("link", { name: /Dokument 7/ }).getAttribute("href")).toBe("/ner/7");
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/entity_events", {
    headers: { "x-api-key": "test-key" }, params: { q: "gal", limit: 50, offset: 0 } }));
});

it("explains an empty result", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 0, events: [] } });
  render(<MemoryRouter><WorldEvents /></MemoryRouter>);
  expect(await screen.findByText("Brak wydarzeń.")).toBeTruthy();
});
