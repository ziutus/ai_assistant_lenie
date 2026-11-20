import axios from "axios";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import TranscriptSpellcheckPanel from "./transcriptSpellcheckPanel";

vi.mock("axios");
vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.restoreAllMocks(); });
const config = { headers: { "x-api-key": "test-key" }, timeout: 240000 };
const settings = { default_model: "local", saved: false, models: [
  { id: "local", label: "Lokalny" },
  { id: "external", label: "Zewnętrzny", external: true, context_length: 10000,
    input_price_per_million: "1", output_price_per_million: "2", currency: "USD" },
  { id: "unavailable", label: "Niedostępny", available: false, unavailable_reason: "brak klucza" },
] };
const proposals = [
  { original: "spóromyśliwiec", replacement: "spór o myśliwiec", confidence: "high", count: 2, context: "To spóromyśliwiec w tekście." },
  { original: "błont", replacement: "błąd", confidence: "medium", count: 1, context: "To błont." },
  { original: "słofko", replacement: "słówko", confidence: "low", count: 3, context: "To słofko." },
];
const result = { status: "ok", suspects: 3, skipped: {}, proposals, model: "external", model_calls: 2,
  usage: { tokens: 1200, cost: "0.03", currency: "USD" }, rejected: {
    unchanged: 1, unknown_word: 2, too_different: 3, not_words: 1, no_proposal: 1, missing_answer: 1, unparseable_answer: 1, future_code: 1,
  } };
const button = (name: string) => screen.getByRole("button", { name });
async function open(onApplied = vi.fn()) {
  vi.mocked(axios.get).mockResolvedValue({ data: settings });
  render(<TranscriptSpellcheckPanel docId="42" onApplied={onApplied} />);
  fireEvent.click(screen.getByText("Błędy transkrypcji (słownik + model)"));
  await waitFor(() => expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("local"));
  return onApplied;
}
async function propose(data = result) {
  vi.mocked(axios.post).mockResolvedValueOnce({ data });
  fireEvent.click(button("Zaproponuj poprawki"));
  await screen.findByLabelText("Poprawka dla spóromyśliwiec");
}
function confirm() {
  fireEvent.click(screen.getByRole("button", { name: /Zastosuj zaznaczone/ }));
  fireEvent.click(button("Potwierdź"));
}

it("calls nothing before opening, fetches models once and previews suspects without a model call", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: settings });
  render(<TranscriptSpellcheckPanel docId="42" onApplied={vi.fn()} />);
  expect(axios.get).not.toHaveBeenCalled();
  expect(axios.post).not.toHaveBeenCalled();
  const summary = screen.getByText("Błędy transkrypcji (słownik + model)");
  fireEvent.click(summary);
  await waitFor(() => expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("local"));
  expect(axios.get).toHaveBeenCalledExactlyOnceWith("/transcript_spellcheck/model", config);
  fireEvent.click(summary);
  fireEvent.click(summary);
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { suspects: [{ word: "błont", count: 2 }],
    skipped: { capitalized: 1, fillers: 2, short: 3, repeated: 4, over_limit: 5 } } });
  fireEvent.click(button("Znajdź podejrzane słowa"));
  await screen.findByText("błont ×2");
  expect(screen.getByText(/Pominięto: 15/)).toBeTruthy();
  for (const label of ["wielkie litery: 1", "wypełniacze: 2", "krótkie: 3", "powtarzane: 4", "ponad limit: 5"]) expect(screen.getByText(label)).toBeTruthy();
  expect(axios.post).toHaveBeenCalledExactlyOnceWith("/document/42/transcript_spellcheck", { dry_run: true }, config);
  expect(axios.get).toHaveBeenCalledOnce();
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { suspects: [], skipped: {} } });
  fireEvent.click(button("Znajdź podejrzane słowa"));
  await screen.findByText("Nie znaleziono podejrzanych słów.");
});

it("sends the chosen model without preview and shows unchecked proposals, cost and Polish rejection reasons", async () => {
  await open();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "external" } });
  expect(screen.getByRole("note").textContent).toContain("zewnętrznego pośrednika");
  expect((screen.getByRole("option", { name: /niedostępny: brak klucza/ }) as HTMLOptionElement).disabled).toBe(true);
  expect(screen.getByRole("option", { name: /za 1 mln tok.*okno 10 tys/ })).toBeTruthy();
  await propose();
  expect(axios.post).toHaveBeenCalledExactlyOnceWith("/document/42/transcript_spellcheck", { model: "external" }, config);
  expect(screen.getAllByRole("checkbox").every(item => !(item as HTMLInputElement).checked)).toBe(true);
  expect(screen.getByText(/Model zaproponował 3 poprawek.*2 wywołań.*1200 tokenów.*0.03 USD/)).toBeTruthy();
  expect((screen.getByText("Odrzucone przez walidację (11)").closest("details") as HTMLDetailsElement).open).toBe(false);
  for (const label of ["bez zmiany: 1", "wymyślone słowo: 2", "zbyt różne od oryginału: 3", "nie są słowami: 1", "brak propozycji: 1", "brak odpowiedzi: 1", "nieczytelna odpowiedź: 1", "future_code: 1"]) expect(screen.getByText(label)).toBeTruthy();
  expect(document.querySelector("mark")?.textContent).toBe("spóromyśliwiec");
});

it("handles null usage and an absent server default", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { ...settings, default_model: null } });
  render(<TranscriptSpellcheckPanel docId="42" onApplied={vi.fn()} />);
  fireEvent.click(screen.getByText("Błędy transkrypcji (słownik + model)"));
  await waitFor(() => expect(axios.get).toHaveBeenCalledOnce());
  await waitFor(() => expect(screen.queryByText("Przetwarzam…")).toBeNull());
  await propose({ ...result, usage: null } as unknown as typeof result);
  expect(screen.getByText(/\? tokenów · koszt: nieznany/)).toBeTruthy();
  expect(axios.post).toHaveBeenLastCalledWith("/document/42/transcript_spellcheck", {}, config);
});

it("edits and applies only two selected rows sequentially and notifies once", async () => {
  const onApplied = await open();
  await propose();
  fireEvent.change(screen.getByLabelText("Poprawka dla spóromyśliwiec"), { target: { value: "spór o samolot" } });
  fireEvent.click(screen.getByLabelText("Zastosuj poprawkę dla spóromyśliwiec"));
  fireEvent.click(screen.getByLabelText("Zastosuj poprawkę dla słofko"));
  let finish!: (value: unknown) => void;
  vi.mocked(axios.post).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { status: "success" } });
  confirm();
  expect(axios.post).toHaveBeenCalledTimes(2); // proposal + first apply; second waits
  expect(screen.getByText("Przetwarzam…")).toBeTruthy();
  expect(screen.getByRole("combobox").closest("fieldset")?.disabled).toBe(true);
  await act(async () => finish({ data: { status: "success" } }));
  await screen.findByText(/Zastosowano 2 poprawek w tekście/);
  expect(vi.mocked(axios.post).mock.calls.slice(1)).toEqual([
    ["/transcript_corrections/apply", { document_id: 42, dry_run: false, pattern: "spóromyśliwiec", replacement: "spór o samolot" }, config],
    ["/transcript_corrections/apply", { document_id: 42, dry_run: false, pattern: "słofko", replacement: "słówko" }, config],
  ]);
  expect(onApplied).toHaveBeenCalledOnce();
  expect(screen.getAllByText("✓ zastosowano")).toHaveLength(2);
  expect(screen.getAllByRole("checkbox")).toHaveLength(1);
});

it("stops on the second apply error, retains remaining selections and reports partial success with details", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const onApplied = await open();
  await propose();
  fireEvent.click(button("Zaznacz wszystkie"));
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { status: "success" } }).mockRejectedValueOnce({
    config: { method: "post", url: "/transcript_corrections/apply" }, response: { status: 502, data: { message: "Błąd serwera" } },
  });
  confirm();
  await screen.findByText("Szczegóły techniczne");
  expect(screen.getByRole("alert").textContent).toContain("Nie udało się zastosować poprawki: Błąd serwera");
  expect(screen.getByRole("alert").textContent).toContain("POST /transcript_corrections/apply");
  expect(axios.post).toHaveBeenCalledTimes(3);
  expect(onApplied).toHaveBeenCalledOnce();
  expect(screen.getAllByRole("checkbox").map(item => (item as HTMLInputElement).checked)).toEqual([true, true]);
  expect(screen.getByText(/Zastosowano 1 poprawek w tekście/)).toBeTruthy();
});

it("dismisses locally, cancels confirmation and prevents empty replacements", async () => {
  await open();
  await propose();
  fireEvent.click(button("Odrzuć poprawkę dla błont"));
  expect(screen.queryByLabelText("Poprawka dla błont")).toBeNull();
  fireEvent.click(button("Zaznacz wszystkie"));
  fireEvent.click(button("Zastosuj zaznaczone (2)"));
  fireEvent.click(button("Anuluj"));
  expect(screen.queryByRole("button", { name: "Potwierdź" })).toBeNull();
  expect(axios.post).toHaveBeenCalledOnce();
  fireEvent.change(screen.getByLabelText("Poprawka dla słofko"), { target: { value: "  " } });
  expect((button("Zastosuj zaznaczone (2)") as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(button("Odznacz wszystkie"));
  expect((button("Zastosuj zaznaczone (0)") as HTMLButtonElement).disabled).toBe(true);
  await propose();
  expect(screen.queryByLabelText("Poprawka dla błont")).toBeNull();
});

it("sets and resets the default model", async () => {
  await open();
  vi.mocked(axios.put).mockResolvedValue({ data: { ...settings, saved: true } });
  fireEvent.click(button("Ustaw jako domyślny"));
  await screen.findByText("Zapisano model domyślny.");
  expect(axios.put).toHaveBeenLastCalledWith("/transcript_spellcheck/model", { model: "local" }, config);
  fireEvent.click(button("Przywróć domyślny serwera"));
  await screen.findByText("Przywrócono domyślny model serwera.");
  expect(axios.put).toHaveBeenLastCalledWith("/transcript_spellcheck/model", { model: null }, config);
});
