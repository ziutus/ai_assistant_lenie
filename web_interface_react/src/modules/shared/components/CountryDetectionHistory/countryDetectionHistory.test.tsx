import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import axios from "axios";
import CountryDetectionHistory, { type CountryDetection } from "./countryDetectionHistory";

vi.mock("axios");
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); });
const props = { docId: 12, apiUrl: "http://api.test", apiKey: "secret" };
const run: CountryDetection = {
  id: 1, created_at: "2026-11-06T12:00:00Z", trigger: "detect_button", text_source: "document", text_chars: 1234, threshold: 5,
  tags_added: ["pl"], llm_called: true, llm_model: "model", llm_usage_log_id: 42, llm_error: "Brak odpowiedzi", llm_prompt: "Pełne zapytanie", llm_response: "",
  decisions: [
    { country_slug: "de", country_name: "Niemcy", mention_count: 2, decision: "llm_rejected", snippets: null },
    { country_slug: "pl", country_name: "Polska", mention_count: 8, decision: "auto_threshold", snippets: ["Cytat o Polsce"] },
    { country_slug: "fr", country_name: "Francja", mention_count: 3, decision: "llm_confirmed", snippets: [] },
    { country_slug: "us", country_name: "USA", mention_count: 1, decision: "abbreviation_confirmed", snippets: [] },
    { country_slug: "cz", country_name: "Czechy", mention_count: 1, decision: "llm_error", snippets: [] },
  ],
};
async function open() {
  fireEvent.click(screen.getByText("Dlaczego te państwa? (historia wykrywania)"));
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
}
it("loads lazily, sorts decisions, renders audit labels and copies the exact payload", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  vi.mocked(axios.get).mockResolvedValue({ data: { detections: [run] } });
  render(<CountryDetectionHistory {...props} />);
  expect(axios.get).not.toHaveBeenCalled();
  await open();
  await screen.findByText("LLM potwierdził");
  const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
  expect(rows.map(r => within(r).getAllByRole("cell")[0].textContent)).toEqual(["Polska", "Francja", "Niemcy", "USA", "Czechy"]);
  for (const text of ["LLM odrzucił", "Skrót potwierdzony", "Błąd LLM — nie oznaczono", "Co najmniej 5 wzmianek — bez LLM", "(pusta odpowiedź)", "Cytat o Polsce"]) expect(screen.getByText(text)).toBeTruthy();
  fireEvent.click(screen.getByText("Pełny prompt"));
  fireEvent.click(screen.getByRole("button", { name: "Kopiuj prompt" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("Pełne zapytanie"));
  fireEvent.click(screen.getByText("Surowa odpowiedź modelu"));
  fireEvent.click(screen.getByRole("button", { name: "Kopiuj odpowiedź" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(""));
  expect(axios.get).toHaveBeenCalledWith("http://api.test/document/12/country_detections?limit=5", { headers: { "x-api-key": "secret" } });
});
it("refreshes activated history on detection id, even when closed, and resets for another document", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { detections: [{ ...run, llm_called: false, tags_added: [] }] } });
  const view = render(<CountryDetectionHistory {...props} />);
  view.rerender(<CountryDetectionHistory {...props} detectionId={2} />);
  expect(axios.get).not.toHaveBeenCalled();
  await open();
  await screen.findByText(/LLM nie był pytany/);
  expect(screen.getByText("nic nowego")).toBeTruthy();
  expect(screen.queryByText("Wywołanie LLM")).toBeNull();
  fireEvent.click(screen.getByText("Dlaczego te państwa? (historia wykrywania)"));
  view.rerender(<CountryDetectionHistory {...props} detectionId={3} />);
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
  view.rerender(<CountryDetectionHistory {...props} docId={13} />);
  expect(screen.queryByText(/LLM nie był pytany/)).toBeNull();
  expect(axios.get).toHaveBeenCalledTimes(2);
});
it("shows empty history", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { detections: [] } });
  render(<CountryDetectionHistory {...props} />); await open();
  expect(await screen.findByText("Brak zapisanej historii wykrywania państw dla tego dokumentu.")).toBeTruthy();
});
it("shows request diagnostics and retries", async () => {
  vi.mocked(axios.get).mockRejectedValueOnce({ code: "ERR_NETWORK", config: { method: "get", url: "http://api.test/document/12/country_detections?limit=5" } })
    .mockResolvedValueOnce({ data: { detections: [] } });
  render(<CountryDetectionHistory {...props} />); await open();
  expect(await screen.findByText(/Nie udało się pobrać historii/, { selector: "p" })).toBeTruthy();
  expect(screen.getByText(/Żądanie: GET.*country_detections/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));
  expect(await screen.findByText("Brak zapisanej historii wykrywania państw dla tego dokumentu.")).toBeTruthy();
});
