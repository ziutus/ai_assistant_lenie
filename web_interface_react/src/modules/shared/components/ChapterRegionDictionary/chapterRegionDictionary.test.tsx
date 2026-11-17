import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChapterRegionDictionary from "./chapterRegionDictionary";
import type { RegionDictionaryInfo } from "../../utils/regionDictionary";

vi.mock("axios");

const info = (overrides: Partial<RegionDictionaryInfo> = {}): RegionDictionaryInfo => ({
  author: "Kanał",
  dictionaries: [{ country_slug: "kraj-jemen", country_name: "Jemen", rules: 16 }],
  pending_changes: 0,
  applications: [
    { rule_id: 2, scope: "region", country_slug: "kraj-jemen", original_text: "Tais", replacement_text: "Taiz",
      chapter_position: 2, occurrences: 16, applied_at: null },
    { rule_id: 3, scope: "region", country_slug: "kraj-jemen", original_text: "huti", replacement_text: "Huti",
      chapter_position: 2, occurrences: 14, applied_at: null },
    { rule_id: 3, scope: "region", country_slug: "kraj-jemen", original_text: "huti", replacement_text: "Huti",
      chapter_position: 2, occurrences: 1, applied_at: null },
    { rule_id: 4, scope: "region", country_slug: "kraj-jemen", original_text: "Marip", replacement_text: "Marib",
      chapter_position: 5, occurrences: 2, applied_at: null },
  ],
  ...overrides,
});

const show = (value: RegionDictionaryInfo | null, position = 2, onChanged = vi.fn()) => {
  render(<MemoryRouter><ChapterRegionDictionary documentId="11263" position={position} info={value}
    apiUrl="" apiKey="k" onChanged={onChanged} /></MemoryRouter>);
  return onChanged;
};

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

it("lists what the dictionary changed in THIS chapter, merged per wording and most frequent first", () => {
  show(info());
  const note = screen.getByRole("note", { name: "Słownik regionu" });
  expect(note.textContent).toContain("Słownik regionu „Jemen” — w tym rozdziale zastosowano (2):");
  const list = within(note).getByRole("list", { name: "Zmiany słownika regionu w tym rozdziale" });
  const lines = within(list).getAllByRole("listitem").map((item) => item.textContent);
  // two rows of the same wording (14 + 1) are one line
  expect(lines).toEqual(["Tais → Taiz ×16", "huti → Huti ×15"]);
  // another chapter's change is in the document-wide list below, not in this chapter's list
  expect(list.textContent).not.toContain("Marip");
});

it("says so when the chapter was not changed and links to the dictionary page", () => {
  show(info(), 7);
  const note = screen.getByRole("note", { name: "Słownik regionu" });
  expect(note.textContent).toContain("Słownik regionu nie zmieniał tego rozdziału");
  expect(within(note).getByRole("link", { name: /Słowniki →/ }).getAttribute("href")).toBe("/dictionaries?tab=region");
});

it("draws nothing without a region dictionary", () => {
  show(null);
  expect(screen.queryByRole("note", { name: "Słownik regionu" })).toBeNull();
  cleanup();
  show(info({ dictionaries: [], applications: [], pending_changes: 0 }));
  expect(screen.queryByRole("note", { name: "Słownik regionu" })).toBeNull();
});

it("previews the remaining changes first and writes only after the explicit save", async () => {
  vi.mocked(axios.post).mockImplementation(async (url: string, body?: unknown) => {
    if (url.endsWith("/transcript_corrections/apply")) {
      const dry = (body as { dry_run: boolean }).dry_run;
      return { data: { status: "success", dry_run: dry, fields: { text: { snippet: { before: "zdobyli Tais.", after: "zdobyli Taiz." } } } } };
    }
    return { data: { status: "success" } };
  });
  const onChanged = show(info({ pending_changes: 52 }));
  expect(screen.getByText(/jeszcze/).textContent).toContain("52");

  fireEvent.click(screen.getByRole("button", { name: "Zastosuj słownik regionu…" }));
  const preview = await screen.findByRole("group", { name: "Podgląd poprawek słownika regionu" });
  expect(preview.textContent).toContain("przed: …zdobyli Tais.…");
  expect(preview.textContent).toContain("po:    …zdobyli Taiz.…");
  expect(vi.mocked(axios.post)).toHaveBeenCalledTimes(1);
  expect(vi.mocked(axios.post).mock.calls[0][1]).toEqual({ document_id: 11263, dry_run: true });

  fireEvent.click(screen.getByRole("button", { name: "Zapisz zmiany w tekście" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  const calls = vi.mocked(axios.post).mock.calls;
  expect(calls[1][1]).toEqual({ document_id: 11263, dry_run: false });
  // entities are refreshed by default (form-encoded id, like the editor's button)
  expect(String(calls[2][0])).toBe("/website_entities");
  expect(String(calls[2][1])).toBe("id=11263");
  expect(await screen.findByText(/encje odświeżone/)).toBeTruthy();
});

it("can skip the entity refresh and reports a failed save without calling it done", async () => {
  vi.mocked(axios.post).mockImplementation(async (url: string, body?: unknown) => {
    if ((body as { dry_run?: boolean })?.dry_run === false) throw Object.assign(new Error("x"), { response: { data: { message: "Brak uprawnień" } } });
    return { data: { fields: { text: { snippet: { before: "a", after: "b" } } } } };
  });
  const onChanged = show(info({ pending_changes: 3 }));
  fireEvent.click(screen.getByRole("button", { name: "Zastosuj słownik regionu…" }));
  await screen.findByRole("group", { name: "Podgląd poprawek słownika regionu" });
  fireEvent.click(screen.getByLabelText(/Odśwież encje po zapisie/));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz zmiany w tekście" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Brak uprawnień");
  expect(onChanged).not.toHaveBeenCalled();
  expect(vi.mocked(axios.post).mock.calls.some(([url]) => String(url).endsWith("/website_entities"))).toBe(false);
});

it("shows what each country's dictionary changed in the whole document, with the chapters", () => {
  show(info());
  const note = screen.getByRole("note", { name: "Słownik regionu" });
  const summary = within(note).getByText(/Słowniki regionów dokumentu \(1\)/);
  expect(summary.textContent).toContain("Jemen: 33 zmian w dokumencie");
  const group = within(note).getByRole("group", { name: "Słownik regionu Jemen" });
  expect(group.textContent).toContain("16 reguł, zmian w całym dokumencie: 33");
  expect(within(group).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "Tais → Taiz ×16 (rozdz. 2)", "huti → Huti ×15 (rozdz. 2)", "Marip → Marib ×2 (rozdz. 5)",
  ]);
});

it("lists the chapters of a change that happened in several, and calls chapter 0 the introduction", () => {
  show(info({ applications: [
    { rule_id: 2, scope: "region", country_slug: "kraj-jemen", original_text: "Tais", replacement_text: "Taiz",
      chapter_position: 4, occurrences: 1, applied_at: null },
    { rule_id: 2, scope: "region", country_slug: "kraj-jemen", original_text: "Tais", replacement_text: "Taiz",
      chapter_position: 0, occurrences: 2, applied_at: null },
    { rule_id: 2, scope: "region", country_slug: "kraj-jemen", original_text: "Tais", replacement_text: "Taiz",
      chapter_position: 2, occurrences: 3, applied_at: null },
  ] }));
  const group = within(screen.getByRole("note", { name: "Słownik regionu" })).getByRole("group", { name: "Słownik regionu Jemen" });
  expect(within(group).getByRole("listitem").textContent).toBe("Tais → Taiz ×6 (rozdz. wstęp, 2, 4)");
});

it("says a dictionary changed nothing yet, and still lists a country known only from old audit rows", () => {
  show(info({ applications: [] }));
  const group = screen.getByRole("group", { name: "Słownik regionu Jemen" });
  expect(group.textContent).toContain("Ten słownik nie zmienił jeszcze tekstu tego dokumentu.");
  cleanup();
  show(info({ dictionaries: [], applications: [
    { rule_id: null, scope: null, country_slug: "kraj-iran", original_text: "Tehran", replacement_text: "Teheran",
      chapter_position: 2, occurrences: 1, applied_at: null },
  ] }));
  expect(screen.getByRole("group", { name: "Słownik regionu iran" }).textContent).toContain("Tehran → Teheran ×1 (rozdz. 2)");
});

it("offers nothing to apply when the dictionary has no pending changes", () => {
  show(info({ pending_changes: 0 }));
  expect(screen.queryByRole("button", { name: "Zastosuj słownik regionu…" })).toBeNull();
});
