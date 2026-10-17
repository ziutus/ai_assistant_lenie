import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChapterBoundariesPanel from "./chapterBoundariesPanel";

vi.mock("axios");
vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const rows = (position: number) => [1, 2, 3, 4].map(index => ({ index, text: "Rozdział " + position + ", zdanie " + index + "." }));
const sections = [1, 2, 3].map(position => ({ position, title: "Temat " + position, sentence_count: 4, sentences: rows(position) }));
const data = { sections, has_embeddings: false, has_analysis_runs: true };
const sentenceCalls = () => vi.mocked(axios.get).mock.calls.filter(([url]) => url.endsWith("/sentences"));
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data });
  vi.mocked(axios.post).mockResolvedValue({ data: { ...data, stale_analysis_runs: 2 } });
});

async function open(disabled = false, defaultOpen = true) {
  const onSaved = vi.fn().mockResolvedValue(undefined);
  const onBusyChange = vi.fn();
  const onFormSubmit = vi.fn(event => event.preventDefault());
  render(<MemoryRouter><form onSubmit={onFormSubmit}>
    <ChapterBoundariesPanel docId="42" onSaved={onSaved} disabled={disabled} defaultOpen={defaultOpen} onBusyChange={onBusyChange} />
  </form></MemoryRouter>);
  if (!defaultOpen) {
    expect(axios.get).not.toHaveBeenCalled();
    screen.getByText("Granice rozdziałów").closest("details")!.open = true;
  }
  await screen.findByText("#1 Temat 1 · 4 zdań");
  await idle();
  return { onSaved, onFormSubmit, onBusyChange };
}
const idle = () => waitFor(() => expect(screen.queryByText("Przetwarzam…")).toBeNull());
async function expand(position: number) {
  const toggle = screen.queryByRole("button", { name: "Rozwiń rozdział " + position });
  if (toggle) fireEvent.click(toggle);
  await screen.findByText("Rozdział " + position + ", zdanie 1.");
  await idle();
  return screen.getByRole("region", { name: "Rozdział " + position + ": Temat " + position });
}
const row = (chapter: HTMLElement, index: number) => within(chapter).getByLabelText("Zdanie " + index);

it("loads all chapters expanded on mount in one request and keeps collapse toggles local", async () => {
  await open();
  expect(axios.get).toHaveBeenCalledTimes(1);
  expect(sentenceCalls()).toHaveLength(0);
  expect(axios.get).toHaveBeenCalledWith("/document/42/chapter_sections", {
    headers: { "x-api-key": "test-key" }, params: { with_sentences: 1 },
  });
  for (const position of [1, 2, 3]) expect(screen.getByText("Rozdział " + position + ", zdanie 4.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Zwiń rozdział 2" }));
  expect(screen.queryByText("Rozdział 2, zdanie 1.")).toBeNull();
  expect(screen.getByText("Rozdział 1, zdanie 1.")).toBeTruthy();
  await expand(2);
  expect(axios.get).toHaveBeenCalledTimes(1);
});

it("also loads all chapters when a collapsed panel is opened", async () => {
  await open(false, false);
  expect(axios.get).toHaveBeenCalledTimes(1);
  expect(screen.getAllByRole("button", { name: /Zwiń rozdział/ })).toHaveLength(3);
});

it.each([
  ["poprzedniego", 2, 2, 2],
  ["następnego", 3, 3, -2],
])("moves the chosen run to %s and refreshes expanded chapters", async (direction, index, position, count) => {
  const { onSaved } = await open();
  await expand(1);
  fireEvent.click(screen.getByRole("button", { name: "Zwiń rozdział 3" }));
  const chapter = await expand(2);
  fireEvent.click(within(row(chapter, index)).getByRole("button", { name: new RegExp("Przenieś do " + direction) }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  await idle();
  expect(axios.post).toHaveBeenCalledWith("/document/42/move_chapter_boundary", { position, sentences: count },
    { headers: { "x-api-key": "test-key" } });
  expect(axios.get).toHaveBeenCalledTimes(2);
  expect(sentenceCalls()).toHaveLength(0);
  expect(screen.getByRole("button", { name: "Rozwiń rozdział 3" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Zwiń rozdział 1" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Zwiń rozdział 2" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "/chunks/42" }).getAttribute("href")).toBe("/chunks/42");
});

it("opens a split title, submits with Enter without submitting the page form, and re-expands shifted chapters", async () => {
  const { onSaved, onFormSubmit } = await open();
  const chapter = await expand(1);
  fireEvent.click(within(row(chapter, 3)).getByRole("button", { name: /Podziel tutaj/ }));
  const input = screen.getByLabelText("Tytuł nowego rozdziału") as HTMLInputElement;
  expect(input.value).toBe("Temat 1 (cd.)");
  expect(row(chapter, 3).style.borderLeft).toBe("3px solid rgb(249, 115, 22)");
  fireEvent.change(input, { target: { value: "Nowy temat" } });
  vi.mocked(axios.get).mockResolvedValue({ data: { ...data, sections: [
    sections[0], { position: 2, title: "Nowy temat", sentence_count: 2, sentences: rows(2).slice(0, 2) },
    { ...sections[1], position: 3 }, { ...sections[2], position: 4 },
  ], stale_analysis_runs: 2 } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  expect(axios.post).toHaveBeenCalledWith("/document/42/split_chapter", { position: 1, sentence_index: 3, title: "Nowy temat" }, expect.any(Object));
  expect(onFormSubmit).not.toHaveBeenCalled();
  expect(await screen.findByText("#2 Nowy temat · 2 zdań")).toBeTruthy();
  await idle();
  expect(screen.getAllByRole("button", { name: /Zwiń rozdział/ })).toHaveLength(4);
  expect(screen.queryByLabelText("Tytuł nowego rozdziału")).toBeNull();
});

it("cancels a split with Escape and restores keyboard focus", async () => {
  await open();
  const chapter = await expand(1);
  const button = within(row(chapter, 2)).getByRole("button", { name: /Podziel tutaj/ });
  fireEvent.click(button);
  fireEvent.keyDown(screen.getByLabelText("Tytuł nowego rozdziału"), { key: "Escape" });
  expect(screen.queryByLabelText("Tytuł nowego rozdziału")).toBeNull();
  expect(document.activeElement).toBe(button);
  expect(axios.post).not.toHaveBeenCalled();
});

it("requires merge confirmation, then saves and re-expands all chapters", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const { onSaved } = await open();
  await expand(2);
  fireEvent.click(screen.getByRole("button", { name: "Zwiń rozdział 1" }));
  const merge = screen.getByRole("button", { name: "Scal rozdział 2 z poprzednim" });
  fireEvent.click(merge);
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Numery kolejnych rozdziałów"));
  expect(axios.post).not.toHaveBeenCalled();
  vi.mocked(axios.get).mockResolvedValue({ data: { ...data, sections: sections.slice(0, 2) } });
  confirm.mockReturnValue(true);
  fireEvent.click(merge);
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  expect(axios.post).toHaveBeenCalledWith("/document/42/merge_chapter", { position: 2 }, expect.any(Object));
  await idle();
  expect(axios.get).toHaveBeenCalledTimes(2);
  expect(screen.getAllByRole("button", { name: /Zwiń rozdział/ })).toHaveLength(2);
});

it("hides illegal actions at chapter and sentence edges", async () => {
  await open();
  const first = await expand(1);
  const middle = await expand(2);
  const last = await expand(3);
  expect(within(first).queryByRole("button", { name: /Scal rozdział/ })).toBeNull();
  expect(within(first).queryByRole("button", { name: /Przenieś do poprzedniego/ })).toBeNull();
  expect(within(last).queryByRole("button", { name: /Przenieś do następnego/ })).toBeNull();
  expect(within(row(middle, 1)).queryByRole("button", { name: /Podziel tutaj/ })).toBeNull();
  expect(within(row(middle, 1)).queryByRole("button", { name: /Przenieś do następnego/ })).toBeNull();
  expect(within(row(middle, 4)).queryByRole("button", { name: /Przenieś do poprzedniego/ })).toBeNull();
});

it("honors the disabled prop for edits", async () => {
  await open(true);
  const chapter = await expand(2);
  const actions = within(row(chapter, 2)).getAllByRole("button") as HTMLButtonElement[];
  expect(actions.every(button => button.disabled)).toBe(true);
  expect((screen.getByRole("button", { name: "Scal rozdział 2 z poprzednim" }) as HTMLButtonElement).disabled).toBe(true);
});

it("locks all actions during a save and ignores repeated clicks", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(axios.post).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  await open();
  const chapter = await expand(2);
  const up = within(row(chapter, 2)).getByRole("button", { name: /Przenieś do poprzedniego/ });
  fireEvent.click(up);
  fireEvent.click(up);
  expect((up as HTMLButtonElement).disabled).toBe(true);
  expect(axios.post).toHaveBeenCalledTimes(1);
  finish({ data: { ...data, stale_analysis_runs: 0 } });
  await idle();
});

it.each([
  ["Document has embeddings.", "Dokument ma embeddingi"],
  ["Document analysis is currently running", "Trwa analiza dokumentu"],
])("shows a Polish 409 message for %s", async (message, expected) => {
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 409, data: { message } } });
  const { onSaved } = await open();
  const chapter = await expand(2);
  fireEvent.click(within(row(chapter, 1)).getByRole("button", { name: /Przenieś do poprzedniego/ }));
  expect((await screen.findByRole("alert")).textContent).toContain(expected);
  expect(onSaved).not.toHaveBeenCalled();
});
