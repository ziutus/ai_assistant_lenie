import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NerChapters from "./nerChapters";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});
// The real panel owns the action menus and dialogs (covered by its own tests); here it only
// reports its first load and hands the page a renderGroups() that lists the entity names.
vi.mock("../components/EntitiesPanel/entitiesPanel", async () => {
  const React = await import("react");
  return {
    default: ({ chapterRenderer, onEntitiesChanged, onShowInText }: any) => {
      React.useEffect(() => { onEntitiesChanged?.(); }, []);
      return <div data-testid="panel">
        <button type="button" onClick={() => onShowInText?.(
          { id: 2, text: "Kijów", variants: ["Kijów", "Kijowie"], chapter_variants: ["Kijowie"] }, "place")}>pokaż Kijów</button>
        {chapterRenderer((source: any) => (
        <ul aria-label="Encje rozdziału">
          {[...(source?.persName ?? []), ...(source?.geogName ?? []), ...(source?.orgName ?? [])]
            .map((item: any) => <li key={item.id}>{item.text}</li>)}
        </ul>
      ))}</div>;
    },
  };
});

const emptyGroups = { persName: [], orgName: [], geogName: [], placeName: [] };
const sections = [
  { position: 1, title: "Wstęp", type: "TEMAT", sentence_count: 2, sentences: [
    { index: 1, text: "Tusk był w Kijowie." }, { index: 2, text: "Nic więcej." },
  ] },
  { position: 2, title: "Sponsor", type: "REKLAMA", sentence_count: 1, sentences: [{ index: 1, text: "Kup teraz." }] },
  { position: 3, title: "Pusty", type: "TEMAT", sentence_count: 1, sentences: [{ index: 1, text: "Bez nazw własnych." }] },
];
const entities = {
  sections: [
    { position: 1, type: "TEMAT", entities: {
      ...emptyGroups,
      persName: [{ id: 1, text: "Donald Tusk", count: 1, variants: ["Tusk"], chapter_variants: ["Tusk"] }],
      geogName: [{ id: 2, text: "Kijów", count: 1, variants: ["Kijów", "Kijowie"], chapter_variants: ["Kijowie"] }],
    } },
    { position: 2, type: "REKLAMA", entities: emptyGroups },
    { position: 3, type: "TEMAT", entities: emptyGroups },
  ],
  has_entities: true,
};

const entityCalls = () => vi.mocked(axios.get).mock.calls.filter(([url]) => String(url).endsWith("/chapter_entities"));

function mockApi(overrides: Record<string, unknown> = {}) {
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url in overrides) {
      const value = overrides[url];
      if (value instanceof Error) throw value;
      return { data: value };
    }
    if (url.endsWith("/chapter_sections")) return { data: { sections } };
    if (url.endsWith("/chapter_entities")) return { data: entities };
    if (url.endsWith("/website_get")) return { data: { title: "Film testowy", document_type: "youtube" } };
    if (url.endsWith("/ner_channel_glossary/applications")) return { data: { author: null, entries: [], applications: [] } };
    throw new Error("unexpected " + url);
  });
}

async function open() {
  render(<MemoryRouter initialEntries={["/ner/42"]}><Routes><Route path="/ner/:id" element={<NerChapters />} /></Routes></MemoryRouter>);
  await screen.findByRole("region", { name: "#1 Wstęp" });
}

beforeEach(() => { vi.resetAllMocks(); mockApi(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("shows chapters with highlighted mentions, entity chips and skipped chapters", async () => {
  await open();
  const chapter = screen.getByRole("region", { name: "#1 Wstęp" });
  const marks = [...chapter.querySelectorAll("mark")];
  expect(marks.map(mark => [mark.textContent, mark.getAttribute("title")])).toEqual([
    ["Tusk", "Donald Tusk (Osoby)"],
    ["Kijowie", "Kijów (Miejsca)"],
  ]);
  expect(within(chapter).getByText("2 zdań · 2 encji")).toBeTruthy();
  expect(within(within(chapter).getByLabelText("Encje rozdziału")).getAllByRole("listitem").map(item => item.textContent))
    .toEqual(["Donald Tusk", "Kijów"]);
  const skipped = screen.getByRole("region", { name: "#2 Sponsor" });
  expect(within(skipped).getByText("Rozdział pominięty w NER (typ: Reklama).")).toBeTruthy();
  expect(skipped.querySelector("mark")).toBeNull();
  expect(within(screen.getByRole("region", { name: "#3 Pusty" })).getByText("Brak encji w tym rozdziale.")).toBeTruthy();
});

it("shows a loading note instead of zero entities until the entity request answers", async () => {
  let finish!: (value: unknown) => void;
  const pendingEntities = new Promise(resolve => { finish = resolve; });
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/chapter_entities")) return pendingEntities as never;
    if (url.endsWith("/chapter_sections")) return { data: { sections } };
    return { data: { title: "Film testowy", document_type: "youtube" } };
  });
  await open();
  const chapter = screen.getByRole("region", { name: "#1 Wstęp" });
  expect(within(chapter).getByText("2 zdań · wczytuję encje…")).toBeTruthy();
  expect(within(chapter).getByText("Wczytuję encje…")).toBeTruthy();
  expect(within(chapter).queryByText("Brak encji w tym rozdziale.")).toBeNull();
  finish({ data: entities });
  expect(await within(chapter).findByText("2 zdań · 2 encji")).toBeTruthy();
});

it("links to the editor, chunks and reader and names the document", async () => {
  await open();
  await screen.findByText("Film testowy");
  expect(screen.getByRole("link", { name: "← Edytor" }).getAttribute("href")).toBe("/youtube/42");
  expect(screen.getByRole("link", { name: "Chunki →" }).getAttribute("href")).toBe("/chunks/42");
  expect(screen.getByRole("link", { name: "Czytnik" }).getAttribute("href")).toBe("/read/42");
});

it("hides a kind of entity from both the highlights and the chips", async () => {
  await open();
  fireEvent.click(screen.getByRole("checkbox", { name: "Osoby" }));
  const chapter = screen.getByRole("region", { name: "#1 Wstęp" });
  expect([...chapter.querySelectorAll("mark")].map(mark => mark.textContent)).toEqual(["Kijowie"]);
  expect(within(within(chapter).getByLabelText("Encje rozdziału")).getAllByRole("listitem").map(item => item.textContent))
    .toEqual(["Kijów"]);
});

it("filters chapters by entity name and by having entities", async () => {
  await open();
  fireEvent.click(screen.getByRole("checkbox", { name: "Tylko rozdziały z encjami" }));
  expect(screen.queryByRole("region", { name: "#2 Sponsor" })).toBeNull();
  expect(screen.queryByRole("region", { name: "#3 Pusty" })).toBeNull();
  expect(screen.getByRole("region", { name: "#1 Wstęp" })).toBeTruthy();

  fireEvent.change(screen.getByRole("searchbox", { name: "Szukaj encji" }), { target: { value: "kijów" } });
  const chapter = screen.getByRole("region", { name: "#1 Wstęp" });
  expect([...chapter.querySelectorAll("mark")].map(mark => mark.textContent)).toEqual(["Kijowie"]);

  fireEvent.change(screen.getByRole("searchbox", { name: "Szukaj encji" }), { target: { value: "xyz" } });
  expect(screen.getByText("Żaden rozdział nie spełnia filtrów.")).toBeTruthy();
});

it("refetches the chapter entities after the panel reports a change", async () => {
  await open();
  // The mocked panel reports its first load, like the real one does after /website_entities.
  await waitFor(() => expect(entityCalls().length).toBe(2));
});

it("names the country a chapter is about without listing it among the chips", async () => {
  const withCountry = { ...entities, sections: entities.sections.map(section => section.position !== 1 ? section : {
    ...section, entities: { ...section.entities, geogName: [
      ...section.entities.geogName,
      { id: 9, text: "Wenezueli", canonical_name: "Wenezuela", count: 3, variants: ["Wenezueli"], chapter_variants: ["Wenezueli"], is_country: true },
    ] },
  }) };
  const sentenceWithCountry = [{ ...sections[0], sentences: [...sections[0].sentences, { index: 3, text: "Rząd Wenezueli upadł." }] },
    ...sections.slice(1)];
  mockApi({ "/document/42/chapter_entities": withCountry, "/document/42/chapter_sections": { sections: sentenceWithCountry } });
  await open();
  const chapter = screen.getByRole("region", { name: "#1 Wstęp" });
  expect([...chapter.querySelectorAll("mark")].map(mark => [mark.textContent, mark.getAttribute("title")])).toContainEqual(
    ["Wenezueli", "Wenezuela (Państwa)"]);
  fireEvent.click(screen.getByRole("checkbox", { name: "Państwa" }));
  expect([...chapter.querySelectorAll("mark")].map(mark => mark.textContent)).not.toContain("Wenezueli");
  fireEvent.click(screen.getByRole("checkbox", { name: "Państwa" }));
  expect(within(within(chapter).getByLabelText("Państwa rozdziału")).getByText("🌍 Wenezuela")).toBeTruthy();
  expect(within(chapter).getByText("2 zdań · 2 encji")).toBeTruthy();
  expect(within(within(chapter).getByLabelText("Encje rozdziału")).getAllByRole("listitem").map(item => item.textContent))
    .toEqual(["Donald Tusk", "Kijów"]);
  expect(within(screen.getByRole("region", { name: "#3 Pusty" })).queryByLabelText("Państwa rozdziału")).toBeNull();
});

it("merges a chapter with its neighbour and reloads the chapters", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  await open();
  const sectionCalls = () => vi.mocked(axios.get).mock.calls.filter(([url]) => String(url).endsWith("/chapter_sections")).length;
  const before = sectionCalls();
  const first = screen.getByRole("region", { name: "#1 Wstęp" });
  expect(within(first).queryByRole("button", { name: "Scal rozdział 1 z poprzednim" })).toBeNull();
  fireEvent.click(within(first).getByRole("button", { name: "Scal rozdział 1 z następnym" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/document/42/merge_chapter", { position: 2 },
    { headers: { "x-api-key": "test-key" } }));
  await waitFor(() => expect(sectionCalls()).toBe(before + 1));
  expect(within(screen.getByRole("region", { name: "#3 Pusty" })).queryByRole("button", { name: /z następnym/ })).toBeNull();
});

it("reports a refused merge and does not reload", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.post).mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
  await open();
  fireEvent.click(screen.getByRole("button", { name: "Scal rozdział 3 z poprzednim" }));
  expect(await screen.findByText(/dokument ma embeddingi/)).toBeTruthy();
});

it("explains a document without transcript text", async () => {
  const error = Object.assign(new Error("bad"), { isAxiosError: true, response: { data: { message: "Document has no transcript text" } } });
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  mockApi({ "/document/42/chapter_sections": error });
  render(<MemoryRouter initialEntries={["/ner/42"]}><Routes><Route path="/ner/:id" element={<NerChapters />} /></Routes></MemoryRouter>);
  expect(await screen.findByText("Dokument nie ma tekstu transkrypcji.")).toBeTruthy();
});

it("keeps working when the entity request fails", async () => {
  mockApi({ "/document/42/chapter_entities": new Error("boom") });
  await open();
  expect(await screen.findByText("Nie udało się pobrać encji rozdziałów.")).toBeTruthy();
  expect(screen.getByRole("region", { name: "#1 Wstęp" })).toBeTruthy();
});

it("marks a chapter as noise and deletes only the entities found nowhere else", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.delete).mockResolvedValue({ data: { status: "success" } });
  const shared = { ...entities, sections: entities.sections.map(section => section.position !== 3 ? section : {
    ...section, entities: { ...emptyGroups, geogName: [{ id: 2, text: "Kijów", count: 1, variants: ["Kijów"], chapter_variants: ["Kijów"] }] },
  }) };
  mockApi({ "/document/42/chapter_entities": shared });
  await open();
  await waitFor(() => expect(within(screen.getByRole("region", { name: "#1 Wstęp" })).getByText("2 zdań · 2 encji")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Oznacz rozdział 1 jako szum" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/document/42/chapter_type", { position: 1, type: "SZUM" },
    { headers: { "x-api-key": "test-key" } }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledTimes(1));
  expect(axios.delete).toHaveBeenCalledWith("/website_entities/1",
    { headers: { "x-api-key": "test-key" }, data: { decision: "deleted", reason_code: "irrelevant" } });
});

it("marks one entity's mentions strongly after \"Podświetl w tekście\", even when its kind is filtered out", async () => {
  Element.prototype.scrollIntoView = vi.fn();
  await open();
  fireEvent.click(screen.getByLabelText("Miejsca"));
  expect(document.querySelector("mark")?.textContent).toBe("Tusk");
  fireEvent.click(screen.getByRole("button", { name: "pokaż Kijów" }));
  const marked = document.querySelector("[data-focus-mark]");
  expect(marked?.textContent).toBe("Kijowie");
  expect(screen.getByRole("status").textContent).toContain("Podświetlono w tekście: Kijów");
  expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /wyczyść/ }));
  expect(document.querySelector("[data-focus-mark]")).toBeNull();
});

it("shows the channel name next to the document title", async () => {
  mockApi({ "/website_get": { title: "Film testowy", document_type: "youtube", byline: "Na Wschód od Bliskiego Wschodu" } });
  await open();
  expect(await screen.findByRole("link", { name: "Kanał: Na Wschód od Bliskiego Wschodu" })).toBeTruthy();
});

it("announces the channel glossary and what it repaired in this document", async () => {
  mockApi({ "/ner_channel_glossary/applications": {
    author: "Na Wschód od Bliskiego Wschodu",
    entries: [{ id: 1, canonical_name: "Pete Hegseth", aliases: ["He H"], fuzzy: true }],
    applications: [{ original_text: "Hekset", replacement_text: "Hegseth", occurrences: 10 }],
  } });
  await open();
  const note = await screen.findByRole("note", { name: "Słownik kanału" });
  expect(note.textContent).toContain("Obowiązuje słownik nazw kanału „Na Wschód od Bliskiego Wschodu”");
  expect(note.textContent).toContain("Pete Hegseth");
  expect(note.textContent).toContain("Hekset → Hegseth ×10");
  expect(within(note).getByRole("link", { name: /Słownik kanału/ }).getAttribute("href"))
    .toBe("/ner-glossary?author=Na%20Wsch%C3%B3d%20od%20Bliskiego%20Wschodu");
});

it("says the glossary is empty for a channel without entries and hides the note without a channel", async () => {
  mockApi({ "/ner_channel_glossary/applications": { author: "Inny kanał", entries: [], applications: [] } });
  await open();
  expect((await screen.findByRole("note", { name: "Słownik kanału" })).textContent).toContain("jest pusty");
  cleanup();
  mockApi();
  await open();
  expect(screen.queryByRole("note", { name: "Słownik kanału" })).toBeNull();
});

it("does not offer the noise button on chapters that are already skipped", async () => {
  await open();
  expect(within(screen.getByRole("region", { name: "#2 Sponsor" })).queryByRole("button", { name: /jako szum/ })).toBeNull();
});

const sentenceBlock = () => screen.getByRole("region", { name: "#1 Wstęp" }).querySelector("div[style*='line-height']") as HTMLElement;

it("adds an entity from a selected fragment through the context menu", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { entity_text: "Obwód Kaliningradzki", mention_count: 1 } });
  await open();
  vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "  Nic   więcej " } as Selection);
  fireEvent.contextMenu(sentenceBlock());
  const menu = screen.getByRole("menu", { name: "Dodaj encję z zaznaczenia" });
  fireEvent.change(within(menu).getByLabelText("Nazwa encji"), { target: { value: "Obwód Kaliningradzki" } });
  fireEvent.click(within(menu).getByRole("menuitem", { name: "📍 Miejsce" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    "/document/42/entities/add_mention",
    { text: "Nic więcej", entity_type: "placeName", name: "Obwód Kaliningradzki" },
    { headers: { "x-api-key": "test-key" } },
  ));
  expect(await screen.findByText("Dodano „Obwód Kaliningradzki” (1×).")).toBeTruthy();
  expect(screen.queryByRole("menu")).toBeNull();
});

it("explains that a selected fragment is already an entity", async () => {
  vi.mocked(axios.post).mockRejectedValue(Object.assign(new Error("409"), {
    isAxiosError: true,
    response: { status: 409, data: { code: "entity_exists", entity: { entity_text: "Kijów" } } },
  }));
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  await open();
  vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "Kijowie" } as Selection);
  fireEvent.contextMenu(sentenceBlock());
  fireEvent.click(screen.getByRole("menuitem", { name: "👤 Osoba" }));
  expect((await screen.findByRole("alert")).textContent).toContain("To już encja „Kijów”");
});

it("shows a group of states with its members in the countries row and the tooltip", async () => {
  const withGroup = { ...entities, sections: entities.sections.map((section) => section.position !== 3 ? section : ({
    ...section, country_groups: [{ name: "Państwa bałtyckie", members: ["Litwa", "Łotwa", "Estonia"], variants: ["nazw własnych"], count: 1 }],
  })) };
  mockApi({ "/document/42/chapter_entities": withGroup });
  await open();
  const chapter = screen.getByRole("region", { name: "#3 Pusty" });
  const row = within(chapter).getByLabelText("Państwa rozdziału");
  expect(row.textContent).toContain("Państwa bałtyckie (Litwa, Łotwa, Estonia)");
  const mark = chapter.querySelector("mark") as HTMLElement;
  expect(mark.getAttribute("title")).toBe("Państwa bałtyckie (Państwa) — Obejmuje: Litwa, Łotwa, Estonia");
});

it("keeps the browser menu when nothing is selected", async () => {
  await open();
  vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "" } as Selection);
  expect(fireEvent.contextMenu(sentenceBlock())).toBe(true);
  expect(screen.queryByRole("menu")).toBeNull();
});
