import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChapterBoundariesPanel from "./chapterBoundariesPanel";

vi.mock("axios");
vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});
afterEach(cleanup);
const sections = (left = 4, right = 2) => [
  { position: 0, title: "", sentence_count: 1, first_sentences: ["Wstęp."], last_sentences: ["Wstęp."] },
  { position: 1, title: "Pierwszy", sentence_count: left, first_sentences: ["Pierwsze."], last_sentences: ["Koniec pierwszego."] },
  { position: 2, title: "Drugi", sentence_count: right, first_sentences: ["Początek drugiego."], last_sentences: ["Ostatnie."] },
];
const payload = (left = 4, right = 2) => ({ sections: sections(left, right), has_embeddings: false, has_analysis_runs: true });
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data: payload() });
  vi.mocked(axios.post).mockResolvedValue({ data: { ...payload(5, 1), stale_analysis_runs: 2 } });
});

async function open(onSaved = vi.fn().mockResolvedValue(undefined)) {
  render(<MemoryRouter><ChapterBoundariesPanel docId="42" onSaved={onSaved} /></MemoryRouter>);
  expect(axios.get).not.toHaveBeenCalled();
  const details = screen.getByText("Granice rozdziałów").closest("details")!;
  details.open = true;
  await screen.findByText("Początek drugiego.");
  await waitFor(() => expect(screen.queryByText("Przetwarzam…")).toBeNull());
  return { details, onSaved };
}

it("loads lazily, previews the boundary, saves +1 and reloads the document with a persistent stale notice", async () => {
  const { onSaved, details } = await open();
  expect(screen.getByText("Koniec pierwszego.")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/document/42/chapter_sections"),
    expect.objectContaining({ headers: expect.objectContaining({ "x-api-key": "test-key" }) }));
  fireEvent.click(screen.getByRole("button", { name: /niżej o zdanie/ }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/document/42/move_chapter_boundary"),
    { position: 2, sentences: 1 }, expect.any(Object));
  expect(screen.getByRole("link", { name: "/chunks/42" }).getAttribute("href")).toBe("/chunks/42");
  expect((screen.getByRole("button", { name: /niżej o zdanie/ }) as HTMLButtonElement).disabled).toBe(true);
  details.open = false;
  details.open = true;
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
  expect(screen.getByText(/powstały ze starego podziału/)).toBeTruthy();
});

it("sends negative steps for moving earlier and disables moves that would empty chapters", async () => {
  await open();
  fireEvent.change(screen.getByLabelText("Liczba zdań:"), { target: { value: "3" } });
  expect((screen.getByRole("button", { name: /niżej o 3 zdania/ }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: /wyżej o 3 zdania/ }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.any(String),
    { position: 2, sentences: -3 }, expect.any(Object)));
});

it("blocks both actions while saving and ignores duplicate clicks", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(axios.post).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  await open();
  const down = screen.getByRole("button", { name: /niżej o zdanie/ });
  fireEvent.click(down);
  fireEvent.click(down);
  expect((down as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: /wyżej o zdanie/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(axios.post).toHaveBeenCalledTimes(1);
  finish({ data: { ...payload(), stale_analysis_runs: 0 } });
  await waitFor(() => expect(screen.queryByText("Przetwarzam…")).toBeNull());
});

it("shows a Polish conflict and leaves the document unchanged", async () => {
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 409, data: { message: "Document has embeddings." } } });
  const { onSaved } = await open();
  fireEvent.click(screen.getByRole("button", { name: /niżej o zdanie/ }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Dokument ma embeddingi"));
  expect(onSaved).not.toHaveBeenCalled();
});

it("disables moves when the GET reports embeddings", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { ...payload(), has_embeddings: true } });
  await open();
  expect((screen.getByRole("button", { name: /niżej o zdanie/ }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: /wyżej o zdanie/ }) as HTMLButtonElement).disabled).toBe(true);
});
