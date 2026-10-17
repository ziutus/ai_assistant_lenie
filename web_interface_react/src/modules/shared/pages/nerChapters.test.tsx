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
    default: ({ chapterRenderer, onEntitiesChanged }: any) => {
      React.useEffect(() => { onEntitiesChanged?.(); }, []);
      return <div data-testid="panel">{chapterRenderer((source: any) => (
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
