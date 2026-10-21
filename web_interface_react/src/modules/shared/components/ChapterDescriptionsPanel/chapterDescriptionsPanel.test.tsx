import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChapterDescriptionsPanel from "./chapterDescriptionsPanel";

vi.mock("axios");
afterEach(cleanup);

const URL = "/document/11139/chapter/11/describe_entities";
const DRY_RUN = { data: {
  candidates: [
    { key: "o1", kind: "organization", name: "Bank Światowy", mentions: 4 },
    { key: "p1", kind: "person", name: "Luka Nikulesku", mentions: 7 },
    { key: "p2", kind: "person", name: "Marcel Ciolacu", mentions: 2 },
  ],
  models: [{ id: "Bielik-11B-v3.0-Instruct", label: "Bielik 11B v3.0" }, { id: "openrouter/openai/gpt-4o-mini", label: "GPT-4o mini", external: true }],
  default_model: "Bielik-11B-v3.0-Instruct",
} };
const PROPOSALS = { data: {
  proposals: [
    { key: "o1", kind: "organization", name: "Bank Światowy", mentions: 4, entity_id: 1, registry_id: 10, status: "ok",
      description: "Instytucja finansowa.", error_code: null },
    { key: "p1", kind: "person", name: "Luka Nikulesku", mentions: 7, entity_id: 2, registry_id: 20, status: "ok",
      description: "Rumuński polityk.", error_code: null },
    { key: "p2", kind: "person", name: "Marcel Ciolacu", mentions: 2, entity_id: 3, registry_id: 21,
      status: "insufficient_context", description: null, error_code: null },
  ],
  usage: { tokens: 321, cost: "0.0002", currency: "USD" },
} };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.isAxiosError).mockReturnValue(false);
  vi.mocked(axios.post).mockImplementation(async (_url, body: any) => (body?.dry_run ? DRY_RUN : PROPOSALS));
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
});

const renderPanel = (onSaved = vi.fn()) => {
  render(<ChapterDescriptionsPanel apiUrl="" apiKey="k" docId={11139} position={11} onSaved={onSaved} />);
  return onSaved;
};

it("describes the missing ones with one request and saves only the approved, edited texts", async () => {
  const onSaved = renderPanel();
  fireEvent.click(screen.getByRole("button", { name: /Uzupełnij brakujące opisy/ }));
  expect(await screen.findByText(/Bez opisu \(3\)/)).toBeTruthy();
  expect(axios.post).toHaveBeenCalledWith(URL, { dry_run: true }, expect.any(Object));

  fireEvent.click(screen.getByRole("button", { name: "Generuj opisy" }));
  // One generation request for all three entities, with the chosen model.
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(URL, { model: "Bielik-11B-v3.0-Instruct" }, expect.any(Object)));
  expect(vi.mocked(axios.post).mock.calls.filter(([, body]) => !(body as any).dry_run)).toHaveLength(1);

  expect(await screen.findByLabelText("Opis: Bank Światowy")).toBeTruthy();
  expect(screen.getByText("Rozdział nie wystarcza do opisu.")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Opis: Luka Nikulesku"), { target: { value: "Rumuński polityk, lider partii." } });
  fireEvent.click(screen.getByRole("checkbox", { name: /Bank Światowy/ })); // reviewer rejects this one

  fireEvent.click(screen.getByRole("button", { name: "Zapisz zaznaczone" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  expect(axios.patch).toHaveBeenCalledTimes(1);
  expect(axios.patch).toHaveBeenCalledWith("/persons/20", { description: "Rumuński polityk, lider partii." }, expect.any(Object));
  expect(await screen.findByText("Zapisano 1 opis.")).toBeTruthy();
});

it("saves organizations through the organization registry endpoint", async () => {
  renderPanel();
  fireEvent.click(screen.getByRole("button", { name: /Uzupełnij brakujące opisy/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Generuj opisy" }));
  await screen.findByLabelText("Opis: Bank Światowy");
  fireEvent.click(screen.getByRole("button", { name: "Zapisz zaznaczone" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(2));
  expect(axios.patch).toHaveBeenCalledWith("/organizations/10", { description: "Instytucja finansowa." }, expect.any(Object));
});

it("says so when every organization and person already has a description", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { candidates: [], models: [], default_model: "m" } });
  renderPanel();
  fireEvent.click(screen.getByRole("button", { name: /Uzupełnij brakujące opisy/ }));
  expect(await screen.findByText(/mają już opisy/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Generuj opisy" })).toBeNull();
});

it("tells which models enforce JSON and warns about the ones that do not", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { ...DRY_RUN.data, models: [
    { id: "Bielik-11B-v3.0-Instruct", label: "Bielik", supports_structured_outputs: true },
    { id: "gpt-4o-mini", label: "GPT-4o mini", supports_structured_outputs: false },
  ] } });
  renderPanel();
  fireEvent.click(screen.getByRole("button", { name: /Uzupełnij brakujące opisy/ }));
  await screen.findByRole("button", { name: "Generuj opisy" });
  expect(screen.getByRole("option", { name: /Bielik — schemat JSON ✓/ })).toBeTruthy();
  expect(screen.getByRole("option", { name: /GPT-4o mini — bez schematu JSON/ })).toBeTruthy();
  expect(screen.queryByRole("note")).toBeNull(); // default model enforces the schema
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "gpt-4o-mini" } });
  expect(screen.getByRole("note").textContent).toContain("nie wymusza formatu JSON");
});

it("warns before sending the chapter to an external model", async () => {
  renderPanel();
  fireEvent.click(screen.getByRole("button", { name: /Uzupełnij brakujące opisy/ }));
  await screen.findByRole("button", { name: "Generuj opisy" });
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "openrouter/openai/gpt-4o-mini" } });
  expect(screen.getByRole("note").textContent).toContain("zewnętrznego pośrednika");
});

it("stops at the first failed save and keeps the unsaved ones for another try", async () => {
  vi.mocked(axios.patch).mockRejectedValueOnce(new Error("boom"));
  const onSaved = renderPanel();
  fireEvent.click(screen.getByRole("button", { name: /Uzupełnij brakujące opisy/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Generuj opisy" }));
  await screen.findByLabelText("Opis: Bank Światowy");
  fireEvent.click(screen.getByRole("button", { name: "Zapisz zaznaczone" }));
  expect(await screen.findByText(/Nie udało się zapisać „Bank Światowy”: boom/)).toBeTruthy();
  expect(axios.patch).toHaveBeenCalledTimes(1);
  expect(onSaved).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Opis: Luka Nikulesku")).toBeTruthy();
});
