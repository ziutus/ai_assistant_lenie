import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import FeedItemComment from "./feedItemComment";
import { buildBrief } from "../../pages/feedReview";

vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas:5000", apiKey: "test-key" }) };
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (_url, init) => new Response(JSON.stringify({ review_note: JSON.parse(init.body).note }))));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function editor(initialNote: string | null = "Zapisana notatka") {
  const onSaved = vi.fn();
  const brief = vi.fn(comment => `Brief: ${comment}`);
  render(<FeedItemComment itemId={7} initialNote={initialNote} onSaved={onSaved} buildBrief={brief} />);
  return { onSaved, brief, textarea: screen.getByRole("textbox"), save: screen.getByRole("button", { name: "Zapisz komentarz" }) };
}

it("enables saving only for changes and saves the note with authentication", async () => {
  const { textarea, save, onSaved } = editor();
  expect(save).toHaveProperty("disabled", true);
  expect(textarea).toHaveProperty("rows", 3);
  expect(textarea).toHaveProperty("maxLength", 4000);
  expect(screen.queryByText("● niezapisane zmiany")).toBeNull();
  fireEvent.change(textarea, { target: { value: "Nowy komentarz" } });
  expect(save).toHaveProperty("disabled", false);
  expect(screen.getByText("● niezapisane zmiany")).toBeTruthy();
  expect(screen.getByText(/14\/4000/)).toBeTruthy();
  fireEvent.click(save);
  expect(save).toHaveProperty("disabled", true);
  await screen.findByText("Zapisano komentarz.");
  expect(fetch).toHaveBeenCalledWith("http://nas:5000/feed_items/7/note", expect.objectContaining({
    method: "PATCH", body: JSON.stringify({ note: "Nowy komentarz" }),
    headers: { "x-api-key": "test-key", "Content-Type": "application/json" },
  }));
  expect(onSaved).toHaveBeenCalledWith("Nowy komentarz");
  expect(screen.queryByText("● niezapisane zmiany")).toBeNull();
  expect(save).toHaveProperty("disabled", true);
});

it("keeps an unsaved draft and reports connection failures", async () => {
  vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
  const { textarea, save, onSaved } = editor();
  fireEvent.change(textarea, { target: { value: "Mój szkic" } });
  fireEvent.click(save);
  expect((await screen.findByRole("alert")).textContent).toBe("Nie można połączyć się z API - komentarz NIE został zapisany.");
  expect(textarea).toHaveProperty("value", "Mój szkic");
  expect(save).toHaveProperty("disabled", false);
  expect(screen.getByText("● niezapisane zmiany")).toBeTruthy();
  expect(onSaved).not.toHaveBeenCalled();
});

it("reports an HTTP failure without losing the draft", async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ message: "Brak uprawnień" }), { status: 403 }));
  const { textarea, save, onSaved } = editor();
  fireEvent.change(textarea, { target: { value: "Szkic" } });
  fireEvent.click(save);
  expect((await screen.findByRole("alert")).textContent).toBe("Brak uprawnień");
  expect(textarea).toHaveProperty("value", "Szkic");
  expect(onSaved).not.toHaveBeenCalled();
});

it("saves an empty note as removal", async () => {
  const { textarea, save, onSaved } = editor();
  fireEvent.change(textarea, { target: { value: "" } });
  fireEvent.click(save);
  expect((await screen.findByRole("status")).textContent).toBe("Usunięto komentarz.");
  expect(onSaved).toHaveBeenCalledWith("");
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/7/note"), expect.objectContaining({ body: '{"note":""}' }));
});

it("copies the current unsaved text through buildBrief", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  const { textarea, brief, onSaved } = editor();
  fireEvent.change(textarea, { target: { value: "Jeszcze niezapisany" } });
  fireEvent.click(screen.getByRole("button", { name: "Skopiuj brief dla LLM" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("Brief: Jeszcze niezapisany"));
  expect(brief).toHaveBeenCalledWith("Jeszcze niezapisany");
  expect((await screen.findByRole("status")).textContent).toBe("Skopiowano brief - wklej go do czatu LLM.");
  expect(onSaved).not.toHaveBeenCalled();
});

it("falls back to a temporary textarea when clipboard is unavailable", async () => {
  vi.stubGlobal("navigator", { clipboard: undefined });
  const execCommand = vi.fn(() => {
    expect((document.body.lastElementChild as HTMLTextAreaElement).value).toBe("Brief: Zapisana notatka");
    return true;
  });
  Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand });
  editor();
  fireEvent.click(screen.getByRole("button", { name: "Skopiuj brief dla LLM" }));
  await screen.findByRole("status");
  expect(execCommand).toHaveBeenCalledWith("copy");
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
});

it("builds the specified Markdown with source details and fallbacks", () => {
  const item = { id: 7, feed_source_id: 1, title: "Inicjatywa", url: "https://example.com", summary: null,
    published_at: null, status: "new", saved_at: null, saved_by_user_id: null };
  const brief = buildBrief(item, [], "  ");
  expect(brief).toBe(`# Zadanie na podstawie wpisu z feedu: Inicjatywa

- Źródło: nieznane (nieznane)
- Opublikowano: brak daty
- URL: https://example.com
- Tematy: brak

## Co mnie zainteresowało i co dalej
(brak komentarza)

## Streszczenie wpisu
(brak streszczenia)

## Polecenie
Na podstawie powyższego zrealizuj to, o co proszę w komentarzu. Jeśli komentarz nie wskazuje działania, zaproponuj trzy możliwe następne kroki i zapytaj, który wybrać. Zajrzyj do adresu URL, jeśli możesz, i zaznacz, co pochodzi ze źródła, a co jest Twoim wnioskiem.`);
  const populated = buildBrief({ ...item, summary: "Opis", published_at: "2026-10-25T12:00:00Z" },
    [{ id: 1, name: "Blog", type: "rss", disabled: false }], "  Stwórz dokument  ");
  expect(populated).toContain("- Źródło: Blog (rss)");
  expect(populated).toContain("- Opublikowano: 2026-10-25");
  expect(populated).toContain("\nStwórz dokument\n");
  expect(populated).toContain("\nOpis\n");
});
