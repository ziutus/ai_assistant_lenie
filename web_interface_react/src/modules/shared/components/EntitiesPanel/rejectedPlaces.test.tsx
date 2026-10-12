import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import EntitiesPanel from "./entitiesPanel";

vi.mock("axios");
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async url => ({ data: url.endsWith("enrichment_job") ? { job: null }
    : url.endsWith("ner_context_decisions") ? { items: [{ entity_text: "ALPHĄ", rationale: "To nazwa grupy." }] }
      : { entities: { persName: [], orgName: [], geogName: [], placeName: [
        { id: 1, text: "Alpha", variants: ["Alphą"], count: 1, place_verification_status: "rejected", place_review_reason: "context_not_place" },
        { id: 2, text: "Beta", count: 1, place_verification_status: "rejected", place_review_reason: "rejected_by_user" },
        { id: 3, text: "Huty", count: 1, place_verification_status: "needs_review" },
      ] } } }));
});

it("hides rejected chips, retains review chips, and fetches rationales only on first expansion", async () => {
  render(<MemoryRouter><EntitiesPanel docId={42} /></MemoryRouter>);
  const summary = await screen.findByText("Odrzucone miejsca (2)");
  const disclosure = summary.closest("details")!;
  expect(disclosure.open).toBe(false);
  expect(screen.queryByRole("button", { name: "Alpha" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Beta" })).toBeNull();
  expect(screen.getByRole("button", { name: "Huty" })).toBeTruthy();
  expect(screen.getByText("Wymaga potwierdzenia")).toBeTruthy();
  expect(disclosure.textContent).toContain("odrzucone automatycznie przez klasyfikator kontekstu");
  expect(disclosure.textContent).toContain("odrzucone ręcznie");
  expect(vi.mocked(axios.get).mock.calls.some(([url]) => url.endsWith("ner_context_decisions"))).toBe(false);
  disclosure.open = true;
  fireEvent(disclosure, new Event("toggle"));
  expect(await screen.findByText("To nazwa grupy.")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith("/ner_context_decisions", expect.objectContaining({ params: {
    document_id: 42, entity_type: "placeName", limit: 200, latest_only: true,
  } }));
  disclosure.open = false;
  fireEvent(disclosure, new Event("toggle"));
  disclosure.open = true;
  fireEvent(disclosure, new Event("toggle"));
  await waitFor(() => expect(vi.mocked(axios.get).mock.calls.filter(([url]) => url.endsWith("ner_context_decisions"))).toHaveLength(1));
  expect(screen.getByText("Wszystkie decyzje automatyczne tego dokumentu").getAttribute("href"))
    .toBe("/ner-decisions?document_id=42");
});

it("keeps the panel usable when rationale loading fails", async () => {
  const original = vi.mocked(axios.get).getMockImplementation()!;
  vi.mocked(axios.get).mockImplementation((...args) => args[0].endsWith("ner_context_decisions")
    ? Promise.reject(new Error("offline")) : original(...args));
  render(<MemoryRouter><EntitiesPanel docId={42} /></MemoryRouter>);
  const disclosure = (await screen.findByText("Odrzucone miejsca (2)")).closest("details")!;
  disclosure.open = true;
  fireEvent(disclosure, new Event("toggle"));
  expect(await screen.findByText("Nie udało się pobrać uzasadnień klasyfikatora.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Huty" })).toBeTruthy();
});
