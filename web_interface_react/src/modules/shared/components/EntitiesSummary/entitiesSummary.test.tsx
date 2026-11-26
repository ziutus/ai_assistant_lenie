import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import EntitiesSummary from "./entitiesSummary";

vi.mock("axios");
vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const data = {
  entities: {
    persName: [{ text: "Tusk", count: 2 }],
    orgName: [{ text: "TVN", count: 1 }, { text: "Polska", count: 1, is_country: true }],
    placeName: [{ text: "Aden", count: 1 }, { text: "Zachód", count: 1, place_verification_status: "rejected" }],
  },
  countries: [{ slug: "malta", name_pl: "Malta" }],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url: string) => ({
    data: url.endsWith("/website_entities") ? data : { job: null },
  }));
});
afterEach(cleanup);

it("shows the counts and links to the review page", async () => {
  render(<MemoryRouter><EntitiesSummary docId={11293} /></MemoryRouter>);
  expect(await screen.findByText("Osoby: 1 · Organizacje i źródła: 1 · Miejsca: 1 · Państwa: 1")).toBeTruthy();
  expect(screen.getByRole("link", { name: /Przegląd NER/ }).getAttribute("href")).toBe("/ner/11293");
  expect(screen.queryByText("Tusk")).toBeNull();
});

it("detects entities, reports busy state and reloads the counts", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { refreshed: 3, enrichment_job: null } });
  const busy = vi.fn();
  render(<MemoryRouter><EntitiesSummary docId={11293} onBusyChange={busy} /></MemoryRouter>);
  await screen.findByText(/Osoby: 1/);
  fireEvent.click(screen.getByRole("button", { name: "Wykryj osoby, miejsca i obiekty" }));
  expect(await screen.findByText("Wykryto encje. Trwa ich pełna weryfikacja w tle.")).toBeTruthy();
  expect(axios.post).toHaveBeenCalledWith("/website_entities", { id: 11293 }, expect.objectContaining({ timeout: 600000 }));
  await waitFor(() => expect(busy.mock.calls).toEqual([[true], [false]]));
});

it("explains an unavailable NER service", async () => {
  vi.mocked(axios.post).mockRejectedValue({ response: { data: { ner_unavailable: true } } });
  render(<MemoryRouter><EntitiesSummary docId={11293} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Wykryj osoby, miejsca i obiekty" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Serwis NER jest niedostępny");
});
