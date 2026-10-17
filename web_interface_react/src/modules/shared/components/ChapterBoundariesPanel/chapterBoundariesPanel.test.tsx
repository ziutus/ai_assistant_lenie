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
  vi.spyOn(window, "scrollBy").mockImplementation(() => {});
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

it("loads all chapters expanded on mount with parallel entity loading and keeps collapse toggles local", async () => {
  await open();
  expect(axios.get).toHaveBeenCalledTimes(2);
  expect(sentenceCalls()).toHaveLength(0);
  expect(axios.get).toHaveBeenCalledWith("/document/42/chapter_sections", {
    headers: { "x-api-key": "test-key" }, params: { with_sentences: 1 },
  });
  for (const position of [1, 2, 3]) expect(screen.getByText("Rozdział " + position + ", zdanie 4.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Zwiń rozdział 2" }));
  expect(screen.queryByText("Rozdział 2, zdanie 1.")).toBeNull();
  expect(screen.getByText("Rozdział 1, zdanie 1.")).toBeTruthy();
  await expand(2);
  expect(axios.get).toHaveBeenCalledTimes(2);
});

it("also loads all chapters when a collapsed panel is opened", async () => {
  await open(false, false);
  expect(axios.get).toHaveBeenCalledTimes(2);
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
  expect(axios.get).toHaveBeenCalledTimes(4);
  expect(sentenceCalls()).toHaveLength(0);
  expect(screen.getByRole("button", { name: (direction === "następnego" ? "Zwiń" : "Rozwiń") + " rozdział 3" })).toBeTruthy();
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
  expect(axios.get).toHaveBeenCalledTimes(4);
  expect(screen.getAllByRole("button", { name: /Zwiń rozdział/ })).toHaveLength(2);
});

it("merges a chapter with the next one via merge_chapter of the following position", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const { onSaved } = await open();
  const merge = screen.getByRole("button", { name: "Scal rozdział 1 z następnym" });
  fireEvent.click(merge);
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining("z następnym"));
  expect(axios.post).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  fireEvent.click(merge);
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  expect(axios.post).toHaveBeenCalledWith("/document/42/merge_chapter", { position: 2 }, expect.any(Object));
});

it("has no merge-with-next on the last chapter", async () => {
  await open();
  expect(screen.queryByRole("button", { name: "Scal rozdział 3 z następnym" })).toBeNull();
  expect(screen.getByRole("button", { name: "Scal rozdział 2 z następnym" })).toBeTruthy();
});

it("hides illegal actions at chapter and sentence edges", async () => {
  await open();
  const first = await expand(1);
  const middle = await expand(2);
  const last = await expand(3);
  expect(within(first).queryByRole("button", { name: /Scal rozdział 1 z poprzednim/ })).toBeNull();
  expect(within(last).queryByRole("button", { name: /Scal rozdział 3 z następnym/ })).toBeNull();
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


const regroup = (sizes: number[]) => {
  const allSentences = sections.flatMap(section => section.sentences);
  let offset = 0;
  return sizes.map((size, index) => {
    const sentences = allSentences.slice(offset, offset + size).map((sentence, index) => ({ ...sentence, index: index + 1 }));
    offset += size;
    return { position: index + 1, title: "Temat " + (index + 1), sentence_count: size, sentences };
  });
};

it.each([
  { operation: "up", ordinal: 7, sizes: [6, 2, 4], anchorChapter: 2, endpoint: "move_chapter_boundary" },
  { operation: "down", ordinal: 7, sizes: [4, 2, 6], anchorChapter: 3, endpoint: "move_chapter_boundary" },
  { operation: "split", ordinal: 7, sizes: [4, 2, 2, 4], anchorChapter: 3, endpoint: "split_chapter" },
  { operation: "merge", ordinal: 5, sizes: [8, 4], anchorChapter: 1, endpoint: "merge_chapter" },
])("restores the correct global sentence anchor for $operation after the fresh rows render", async ({ operation, ordinal, sizes, anchorChapter, endpoint }) => {
  await open();
  const oldAnchor = document.querySelector<HTMLElement>('[data-gsi="' + ordinal + '"]')!;
  const originalText = oldAnchor.querySelector('span[style*="white-space"]')!.textContent;
  const chapter = screen.getByRole("region", { name: "Rozdział 2: Temat 2" });
  let refreshed = false;
  const measured: Array<{ ordinal: string | undefined; refreshed: boolean }> = [];
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    measured.push({ ordinal: this.dataset.gsi, refreshed });
    return { top: refreshed ? 180 : 300 } as DOMRect;
  });
  vi.mocked(axios.get).mockImplementation(async () => {
    refreshed = true;
    return { data: { ...data, sections: regroup(sizes) } };
  });
  // Receiving chapters start collapsed; moves must reveal them without losing the anchor.
  if (operation === "up" || operation === "merge") fireEvent.click(screen.getByRole("button", { name: "Zwiń rozdział 1" }));
  if (operation === "down") fireEvent.click(screen.getByRole("button", { name: "Zwiń rozdział 3" }));
  if (operation === "up") {
    fireEvent.click(within(row(chapter, 2)).getByRole("button", { name: /Przenieś do poprzedniego/ }));
  } else if (operation === "down") {
    fireEvent.click(within(row(chapter, 3)).getByRole("button", { name: /Przenieś do następnego/ }));
  } else if (operation === "split") {
    fireEvent.click(within(row(chapter, 3)).getByRole("button", { name: /Podziel tutaj/ }));
    fireEvent.click(screen.getByRole("button", { name: "Podziel" }));
  } else {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Scal rozdział 2 z poprzednim" }));
  }
  await idle();
  expect(axios.post).toHaveBeenCalledWith("/document/42/" + endpoint, expect.any(Object), expect.any(Object));
  expect(measured).toEqual([{ ordinal: String(ordinal), refreshed: false }, { ordinal: String(ordinal), refreshed: true }]);
  expect(window.scrollBy).toHaveBeenCalledExactlyOnceWith(0, -120);
  const newAnchor = document.querySelector<HTMLElement>('[data-gsi="' + ordinal + '"]')!;
  expect(newAnchor.querySelector('span[style*="white-space"]')!.textContent).toBe(originalText);
  expect(newAnchor.closest("section")!.dataset.chapterPosition).toBe(String(anchorChapter));
  expect(screen.getByRole("button", { name: "Zwiń rozdział " + anchorChapter })).toBeTruthy();
});

it("keeps cards and reserved status space mounted throughout the POST and document reload", async () => {
  const { onSaved } = await open();
  const cards = screen.getAllByRole("region", { name: /^Rozdział/ });
  const status = screen.getByRole("status");
  expect(status.style.minHeight).toBe("1.5em");
  let finishPost!: (value: unknown) => void;
  let finishReload!: () => void;
  vi.mocked(axios.post).mockImplementation(() => new Promise(resolve => { finishPost = resolve; }));
  onSaved.mockImplementation(() => new Promise<void>(resolve => { finishReload = resolve; }));
  fireEvent.click(within(row(cards[1], 2)).getByRole("button", { name: /Przenieś do poprzedniego/ }));
  expect(screen.getAllByRole("region", { name: /^Rozdział/ })).toEqual(cards);
  expect(screen.getByText("Przetwarzam…")).toBe(status);
  finishPost({ data: { ...data, stale_analysis_runs: 0 } });
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  // This intermediate render used to setSections([]), unmounting every card.
  expect(screen.getAllByRole("region", { name: /^Rozdział/ })).toEqual(cards);
  expect(screen.getByText("Rozdział 2, zdanie 3.")).toBeTruthy();
  expect(window.scrollBy).not.toHaveBeenCalled();
  finishReload();
  await idle();
  expect(screen.getByRole("status")).toBe(status);
  expect(status.style.minHeight).toBe("1.5em");
});

it("does not restore an obsolete anchor after a failed edit", async () => {
  await open();
  vi.mocked(axios.post).mockRejectedValue(new Error("offline"));
  const chapter = screen.getByRole("region", { name: "Rozdział 2: Temat 2" });
  fireEvent.click(within(row(chapter, 2)).getByRole("button", { name: /Przenieś do poprzedniego/ }));
  await screen.findByRole("alert");
  expect(window.scrollBy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Odśwież" }));
  await idle();
  expect(window.scrollBy).not.toHaveBeenCalled();
});


it.each([
  ["REKLAMA", "Reklama", "rgb(254, 243, 199)"],
  ["SZUM", "Szum", "rgb(229, 231, 235)"],
  ["ZRODLA", "Źródła", "rgb(219, 234, 254)"],
])("changes chapter type to %s and displays its badge", async (type, label, color) => {
  const { onSaved } = await open();
  const select = screen.getByRole("combobox", { name: "Typ rozdziału 2" }) as HTMLSelectElement;
  expect(select.value).toBe("TEMAT");
  expect(within(select).getAllByRole("option").map(option => option.textContent)).toEqual(["Treść", "Reklama", "Szum", "Źródła"]);
  vi.mocked(axios.get).mockResolvedValue({ data: { ...data, sections: sections.map(section => ({
    ...section, type: section.position === 2 ? type : "TEMAT",
  })) } });
  fireEvent.change(select, { target: { value: type } });
  await idle();
  expect(axios.post).toHaveBeenCalledWith("/document/42/chapter_type", { position: 2, type },
    { headers: { "x-api-key": "test-key" } });
  expect(onSaved).toHaveBeenCalledTimes(1);
  expect(axios.get).toHaveBeenCalledTimes(4);
  expect(select.value).toBe(type);
  expect(screen.getByLabelText("Typ: " + label).style.background).toBe(color);
  expect(screen.getByRole("link", { name: "/chunks/42" })).toBeTruthy();
});

it("keeps collapsed chapters and restores the card scroll anchor after a type change", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "Zwiń rozdział 2" }));
  let refreshed = false;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(() => ({ top: refreshed ? 180 : 300 } as DOMRect));
  vi.mocked(axios.get).mockImplementation(async () => { refreshed = true; return { data }; });
  fireEvent.change(screen.getByLabelText("Typ rozdziału 2"), { target: { value: "REKLAMA" } });
  await idle();
  expect(screen.getByRole("button", { name: "Rozwiń rozdział 2" })).toBeTruthy();
  expect(window.scrollBy).toHaveBeenCalledExactlyOnceWith(0, -120);
});

it("locks type changes and ignores repeated change events during a save", async () => {
  await open();
  let finish!: (value: unknown) => void;
  vi.mocked(axios.post).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const select = screen.getByLabelText("Typ rozdziału 1") as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "SZUM" } });
  fireEvent.change(select, { target: { value: "REKLAMA" } });
  expect(select.disabled).toBe(true);
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect((screen.getByLabelText("Typ rozdziału 2") as HTMLSelectElement).disabled).toBe(true);
  finish({ data: { ...data, stale_analysis_runs: 0 } });
  await idle();
});

it.each(["disabled", "embeddings"])("blocks chapter type edits for %s", async reason => {
  if (reason === "embeddings") vi.mocked(axios.get).mockResolvedValue({ data: { ...data, has_embeddings: true } });
  await open(reason === "disabled");
  const select = screen.getByLabelText("Typ rozdziału 1") as HTMLSelectElement;
  expect(select.disabled).toBe(true);
  fireEvent.change(select, { target: { value: "SZUM" } });
  expect(axios.post).not.toHaveBeenCalled();
});

it("keeps the merge type conflict warning after subsequent edits", async () => {
  await open();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { ...data, type_conflict: { kept: "REKLAMA", dropped: "TEMAT" } } });
  fireEvent.click(screen.getByRole("button", { name: "Scal rozdział 2 z poprzednim" }));
  await idle();
  const message = "Scalono rozdziały o różnych typach — zachowano typ: Reklama, pominięto: Treść";
  expect(screen.getByRole("alert").textContent).toContain(message);
  fireEvent.change(screen.getByLabelText("Typ rozdziału 1"), { target: { value: "SZUM" } });
  await idle();
  expect(screen.getByRole("alert").textContent).toContain(message);
});


const entityResponse = (has_entities = true) => ({ has_entities, sections: sections.map(section => ({
  position: section.position, type: "TEMAT", entities: {
    persName: [{ text: "Jan", count: 3 }], geogName: [{ text: "Warszawa", count: 2 }],
    placeName: [], orgName: [{ text: "Firma", count: 1 }],
  },
})) });

it("renders reusable read-only entity chips with local counts", async () => {
  vi.mocked(axios.get).mockImplementation(async url => ({ data: url.endsWith("/chapter_entities") ? entityResponse() : data }));
  await open();
  const chapter = screen.getByRole("region", { name: "Rozdział 1: Temat 1" });
  fireEvent.click(within(chapter).getByText("Encje (3)"));
  expect(within(chapter).getByText("Jan")).toBeTruthy();
  expect(within(chapter).getByText("×3")).toBeTruthy();
  for (const label of ["Osoby:", "Miejsca:", "Organizacje:"]) expect(within(chapter).getByText(label)).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith("/document/42/chapter_entities", { headers: { "x-api-key": "test-key" } });
  expect(axios.post).not.toHaveBeenCalled();
});

it("shows the missing stored entities hint", async () => {
  vi.mocked(axios.get).mockImplementation(async url => ({ data: url.endsWith("/chapter_entities") ? entityResponse(false) : data }));
  await open();
  expect(screen.getAllByText("Brak zapisanych encji — użyj „Wykryj osoby, miejsca i obiekty” poniżej.")).toHaveLength(3);
});

it("shows the excluded chapter type instead of chips", async () => {
  vi.mocked(axios.get).mockImplementation(async url => ({ data: url.endsWith("/chapter_entities") ? entityResponse() : {
    ...data, sections: sections.map(section => ({ ...section, type: "REKLAMA" })),
  } }));
  await open();
  expect(screen.getAllByText("Rozdział pominięty w NER (typ: Reklama)")).toHaveLength(3);
  expect(screen.queryByText("Jan")).toBeNull();
});

it("keeps editing functional when entities fail to load", async () => {
  vi.mocked(axios.get).mockImplementation(async url => {
    if (url.endsWith("/chapter_entities")) throw new Error("offline");
    return { data };
  });
  const { onSaved } = await open();
  expect(screen.getByText("Nie udało się pobrać encji")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Typ rozdziału 1"), { target: { value: "REKLAMA" } });
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  await idle();
  expect(axios.post).toHaveBeenCalledWith("/document/42/chapter_type", { position: 1, type: "REKLAMA" },
    { headers: { "x-api-key": "test-key" } });
  expect(screen.getByText("Zmieniono typ rozdziału — odśwież encje przyciskiem „Wykryj osoby, miejsca i obiekty”.")).toBeTruthy();
  expect(vi.mocked(axios.get).mock.calls.filter(([url]) => url.endsWith("/chapter_entities"))).toHaveLength(2);
});


it("preserves entity details and card nodes across edits without toggling the panel", async () => {
  vi.mocked(axios.get).mockImplementation(async url => ({ data: url.endsWith("/chapter_entities") ? entityResponse() : data }));
  await open();
  const panel = screen.getByText("Granice rozdziałów").closest("details")!;
  const card = screen.getByRole("region", { name: "Rozdział 1: Temat 1" });
  const details = within(card).getByText("Encje (3)").closest("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle", { bubbles: true }));
  fireEvent.change(screen.getByLabelText("Typ rozdziału 1"), { target: { value: "REKLAMA" } });
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
  await idle();
  expect(screen.getByRole("region", { name: "Rozdział 1: Temat 1" })).toBe(card);
  expect(within(card).getByText("Encje (3)").closest("details")).toBe(details);
  expect(details.open).toBe(true);
  details.open = false;
  fireEvent(details, new Event("toggle", { bubbles: true }));
  expect(panel.open).toBe(true);
  expect(axios.get).toHaveBeenCalledTimes(4);
});
