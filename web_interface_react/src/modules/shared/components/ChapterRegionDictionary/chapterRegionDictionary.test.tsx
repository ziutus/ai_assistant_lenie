import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChapterRegionDictionary from "./chapterRegionDictionary";
import type { PendingDictionaryChange, RegionDictionaryInfo } from "../../utils/regionDictionary";

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

const pendingChanges: PendingDictionaryChange[] = [
  { rule_id: 3, scope: "region", country_slug: "kraj-jemen", pattern: "huti", replacement: "Huti",
    occurrences: 4, chapters: [0, 2, 5], wordings: [
      { original: "huti", replacement: "Huti", occurrences: 3 },
      { original: "HUTI", replacement: "Huti", occurrences: 1 },
    ] },
  { rule_id: 2, scope: "region", country_slug: "kraj-jemen", pattern: "Tais", replacement: "Taiz",
    occurrences: 2, chapters: [2, 5], wordings: [{ original: "Tais", replacement: "Taiz", occurrences: 2 }] },
];

const openChangesPreview = async (changes = pendingChanges) => {
  // A snippet must not override the new list, even when the list is empty.
  vi.mocked(axios.post).mockResolvedValue({ data: { changes,
    fields: { text: { snippet: { before: "old snippet", after: "new snippet" } } } } });
  const onChanged = show(info({ pending_changes: 6 }));
  fireEvent.click(screen.getByRole("button", { name: "Zastosuj słownik regionu…" }));
  const preview = await screen.findByRole("group", { name: "Podgląd poprawek słownika regionu" });
  return { onChanged, preview };
};

it("lists all pending rules and wordings, selects them by default and saves all without rule_ids", async () => {
  const { onChanged, preview } = await openChangesPreview();
  const list = within(preview).getByRole("list", { name: "Oczekujące zmiany słownika regionu" });
  const rows = within(list).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[0].textContent).toBe("huti → Huti ×3HUTI → Huti ×1(rozdz. wstęp, 2, 5)");
  expect(rows[1].textContent).toBe("Tais → Taiz ×2(rozdz. 2, 5)");
  expect(within(list).getAllByRole<HTMLInputElement>("checkbox").every((box) => box.checked)).toBe(true);
  expect(preview.textContent).not.toContain("old snippet");
  fireEvent.click(screen.getByRole("button", { name: "Zapisz wybrane zmiany (2 z 2)" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  expect(vi.mocked(axios.post).mock.calls[1][1]).toEqual({ document_id: 11263, dry_run: false });
  expect(vi.mocked(axios.post).mock.calls[2][0]).toBe("/website_entities");
  expect(screen.getByText("Poprawki zapisane w tekście, encje odświeżone.")).toBeTruthy();
});

it.each([true, false])("saves only selected rule ids and reports the subset (refresh entities: %s)", async (refresh) => {
  const { onChanged } = await openChangesPreview();
  fireEvent.click(screen.getByRole("checkbox", { name: "Zapisz zmianę huti → Huti" }));
  if (!refresh) fireEvent.click(screen.getByLabelText(/Odśwież encje po zapisie/));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz wybrane zmiany (1 z 2)" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  expect(vi.mocked(axios.post).mock.calls[1][1]).toEqual({ document_id: 11263, dry_run: false, rule_ids: [2] });
  const message = screen.getByText(/Zapisano 1 z 2 zmian w tekście. Pozostałe czekają na zastosowanie./);
  expect(message.textContent).toContain(refresh ? "Encje odświeżone." : "Odśwież encje („Wykryj osoby i miejsca”)");
  expect(vi.mocked(axios.post)).toHaveBeenCalledTimes(refresh ? 3 : 2);
});

it("prevents saving an empty selection and can select all again", async () => {
  const { onChanged } = await openChangesPreview();
  fireEvent.click(screen.getByRole("button", { name: "Odznacz wszystkie" }));
  const save = screen.getByRole<HTMLButtonElement>("button", { name: "Zapisz wybrane zmiany (0 z 2)" });
  expect(save.disabled).toBe(true);
  expect(screen.getByText("Zaznacz co najmniej jedną zmianę.")).toBeTruthy();
  fireEvent.click(save);
  expect(vi.mocked(axios.post)).toHaveBeenCalledTimes(1);
  expect(onChanged).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Zaznacz wszystkie" }));
  expect(screen.getByRole<HTMLButtonElement>("button", { name: "Zapisz wybrane zmiany (2 z 2)" }).disabled).toBe(false);
  expect(screen.queryByText("Zaznacz co najmniej jedną zmianę.")).toBeNull();
});

it("shows no save button for an empty changes array, even with a legacy snippet", async () => {
  const { preview } = await openChangesPreview([]);
  expect(within(preview).getByText("Brak zmian do zapisania.")).toBeTruthy();
  expect(within(preview).queryByRole("button", { name: /Zapisz/ })).toBeNull();
  expect(preview.textContent).not.toContain("old snippet");
  fireEvent.click(within(preview).getByRole("button", { name: "Anuluj" }));
  expect(screen.queryByRole("group", { name: "Podgląd poprawek słownika regionu" })).toBeNull();
  expect(vi.mocked(axios.post)).toHaveBeenCalledTimes(1);
});

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
