import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import TranscriptChaptersSuggest from "./transcriptChaptersSuggest";

vi.mock("axios");
vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("previews model capacity without auto calling, edits proposals and saves only checked chapters", async () => {
  const onSaved = vi.fn().mockResolvedValue(undefined);
  vi.mocked(axios.post).mockResolvedValueOnce({ data: {
    default_model: "large", candidates: { estimated_tokens: 10000 }, models: [
      { id: "large", label: "Duży", context_length: 100000 },
      { id: "small", label: "Mały", context_length: 4000, external: true,
        candidates: { fits_single_call: false, model_calls: 4 } },
    ],
  } });
  render(<TranscriptChaptersSuggest docId="11172" onSaved={onSaved} />);
  expect(axios.post).not.toHaveBeenCalled();
  expect(screen.getByText(/lenie-youtube-outline 11172/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Wybierz model i zaproponuj rozdziały" }));
  await screen.findByText(/mieści się w całości/);
  expect(axios.post).toHaveBeenCalledWith("/document/11172/suggest_chapters", { dry_run: true }, expect.anything());
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "small" } });
  expect(screen.getByText(/wymaga podziału na okna \(4 wywołań\)/)).toBeTruthy();
  expect(screen.getByRole("note").textContent).toContain("zewnętrznego pośrednika");
  vi.mocked(axios.post).mockResolvedValueOnce({ data: {
    status: "ok", model: "small", model_calls: 4, usage: { tokens: 12000, cost: "0.03", currency: "USD" },
    text_sha256: "snapshot", chapters: [
      { start_sentence: 0, title: "Początek", preview: "Pierwsze zdanie." },
      { start_sentence: 20, title: "Dalej", preview: "Kolejne zdanie." },
    ],
  } });
  fireEvent.click(screen.getByRole("button", { name: "Zaproponuj rozdziały" }));
  await screen.findByText("Pierwsze zdanie.");
  fireEvent.change(screen.getByLabelText("Tytuł rozdziału 1"), { target: { value: "Poprawiony tytuł" } });
  fireEvent.click(screen.getByLabelText("Zapisz rozdział 2"));
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { status: "ok", chapter_count: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz rozdziały" }));
  await screen.findByText("Zapisano rozdziały.");
  expect(axios.post).toHaveBeenLastCalledWith("/document/11172/apply_chapters", {
    chapters: [{ start_sentence: 0, title: "Poprawiony tytuł" }], expected_text_sha256: "snapshot",
  }, { headers: { "x-api-key": "test-key" }, timeout: 240000 });
  expect(onSaved).toHaveBeenCalledOnce();
});

it("sets and resets the household default and shows API errors inline", async () => {
  vi.mocked(axios.post).mockResolvedValueOnce({ data: {
    default_model: "model", candidates: { estimated_tokens: 10 },
    models: [{ id: "model", label: "Model", context_length: 10000 }],
  } });
  render(<TranscriptChaptersSuggest docId="1" onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Wybierz model i zaproponuj rozdziały" }));
  await screen.findByRole("combobox");
  vi.mocked(axios.put).mockResolvedValue({ data: { default_model: "model" } });
  fireEvent.click(screen.getByRole("button", { name: "Ustaw jako domyślny" }));
  await screen.findByText("Zapisano model domyślny.");
  expect(axios.put).toHaveBeenLastCalledWith("/transcript_chapters/model", { model: "model" }, expect.anything());
  fireEvent.click(screen.getByRole("button", { name: "Przywróć domyślny serwera" }));
  await screen.findByText("Przywrócono domyślny model serwera.");
  expect(axios.put).toHaveBeenLastCalledWith("/transcript_chapters/model", { model: null }, expect.anything());
  vi.mocked(axios.post).mockRejectedValueOnce({ response: { data: { message: "Błąd modelu" } } });
  fireEvent.click(screen.getByRole("button", { name: "Zaproponuj rozdziały" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Błąd modelu"));
});
