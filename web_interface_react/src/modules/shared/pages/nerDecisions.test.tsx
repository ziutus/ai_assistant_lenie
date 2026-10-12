import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NerDecisions from "./nerDecisions";

vi.mock("axios");
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 80,
    summary: { total: 80, dropped: 80, by_class: { not_place: 80 } }, items: [{
      id: 1, document_id: 42, document_title: null, entity_text: "Alpha", entity_type: "placeName",
      predicted_class: "not_place", confidence: "high", dropped: true, rationale: "To grupa.",
      context_excerpt: "Długi kontekst", model: "test-model", created_at: "2026-01-01T12:00:00",
    }] } });
});
function Location() { return <output data-testid="location">{useLocation().search}</output>; }

it("restores URL filters, renders decisions and persists pagination and filter changes", async () => {
  render(<MemoryRouter initialEntries={["/ner-decisions?entity_type=placeName&predicted_class=not_place&confidence=high&dropped=true&latest_only=false&q=Alpha&document_id=42&page=2&pageSize=25"]}>
    <NerDecisions /><Location /></MemoryRouter>);
  expect(await screen.findByText("To grupa.")).toBeTruthy();
  expect(axios.get).toHaveBeenLastCalledWith("/ner_context_decisions", expect.objectContaining({ params: {
    limit: 25, offset: 25, entity_type: "placeName", predicted_class: "not_place", confidence: "high",
    dropped: "true", latest_only: "false", q: "Alpha", document_id: "42",
  } }));
  expect(screen.getByRole("link", { name: "#42" }).getAttribute("href")).toBe("/read/42");
  expect(screen.getByText("Długi kontekst").closest("details")!.open).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Następna" }));
  await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith("/ner_context_decisions",
    expect.objectContaining({ params: expect.objectContaining({ offset: 50 }) })));
  expect(screen.getByTestId("location").textContent).toContain("page=3");
  fireEvent.change(screen.getByLabelText("Na stronę"), { target: { value: "50" } });
  await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith("/ner_context_decisions",
    expect.objectContaining({ params: expect.objectContaining({ offset: 0, limit: 50 }) })));
  fireEvent.click(screen.getByLabelText("tylko najnowsze"));
  await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith("/ner_context_decisions",
    expect.objectContaining({ params: expect.objectContaining({ latest_only: "true" }) })));
});

it("defaults to latest decisions and shows the empty state", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 0, items: [], summary: { total: 0, dropped: 0, by_class: {} } } });
  render(<MemoryRouter><NerDecisions /></MemoryRouter>);
  expect(await screen.findByText("Brak decyzji dla wybranych filtrów.")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith("/ner_context_decisions", expect.objectContaining({ params: { limit: 50, offset: 0, latest_only: "true" } }));
});

it("shows a Polish loading and error state", async () => {
  vi.mocked(axios.get).mockRejectedValue(new Error("offline"));
  render(<MemoryRouter><NerDecisions /></MemoryRouter>);
  expect(screen.getByText("Ładowanie decyzji…")).toBeTruthy();
  expect((await screen.findByRole("alert")).textContent).toBe("Nie udało się pobrać decyzji NER.");
});
