import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PromptTemplates from "./promptTemplates";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas:5000", apiKey: "test-key" }) };
});

const template = {
  id: 3, task: "content_group_suggestion", variant: "feed_item", version: 2, label: "feed_item-v2",
  system_template: "SYS", user_template: "Katalog: {{ catalog }} {{ material }}", note: "krótszy", is_active: true, created_at: null,
};
const listing = {
  templates: [template], variables: { catalog: "katalog", material: "materiał", schema: "schemat" },
  builtin: { feed_item: { system_template: "B-SYS", user_template: "B-USER {{ catalog }}" } },
};
const comparison = {
  runs_considered: 3,
  rows: [{
    model: "openrouter/google/gemini-2.5-flash-lite", prompt_version: "feed_item-v2", prompt_template_id: 3, runs: 3,
    avg_prompt_tokens: 900, avg_completion_tokens: 60, avg_latency_ms: 1500,
    cost: { USD: { total: "0.0003", per_run: "0.0001", runs_with_cost: 3, per_accepted: "0.00015" } },
    suggestions: 4, accepted: 2, dismissed: 1, pending: 1, accept_rate: 0.667, no_match_runs: 1, last_run_at: null,
  }],
};

const json = (body: object, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url.includes("/prompt_templates/comparison")) return Promise.resolve(json(comparison));
    if (url.endsWith("/prompt_templates/preview")) return Promise.resolve(json({ system: "S", user: "RENDER", feed_item_id: null }));
    if (url.endsWith("/prompt_templates") && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      return Promise.resolve(body.user_template.includes("{{ zle") ? json({ message: "user_template: syntax" }, 400)
        : json({ template: { ...template, id: 4, version: 3, label: "feed_item-v3" } }, 201));
    }
    if (url.includes("/prompt_templates?")) return Promise.resolve(json(listing));
    return Promise.reject(new TypeError("Failed to fetch"));
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const renderPage = () => render(<MemoryRouter initialEntries={["/prompt-templates"]}><PromptTemplates /></MemoryRouter>);

it("loads the active version into the editor and shows the comparison with cost per 1000 runs", async () => {
  renderPage();
  expect(await screen.findByDisplayValue("Katalog: {{ catalog }} {{ material }}")).toBeTruthy();
  expect(screen.getByDisplayValue("SYS")).toBeTruthy();
  expect(await screen.findByText("google/gemini-2.5-flash-lite")).toBeTruthy();
  expect(screen.getByText(/0,1 USD/)).toBeTruthy();
  expect(screen.getByText("67%")).toBeTruthy();
});

it("saves the edited text as a new active version and reports it", async () => {
  renderPage();
  const user = await screen.findByLabelText(/Prompt użytkownika/);
  fireEvent.change(user, { target: { value: "Nowy {{ catalog }}" } });
  expect(screen.getByText(/niezapisane zmiany/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Zapisz jako nową wersję i aktywuj" }));
  expect((await screen.findByRole("status")).textContent).toContain("feed_item-v3");
  const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "POST" && String(init.body).includes("Nowy"));
  expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ variant: "feed_item", activate: true, user_template: "Nowy {{ catalog }}" });
});

it("shows the backend validation message and keeps the draft", async () => {
  renderPage();
  const user = await screen.findByLabelText(/Prompt użytkownika/);
  fireEvent.change(user, { target: { value: "{{ zle" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz jako nową wersję i aktywuj" }));
  expect((await screen.findByRole("alert")).textContent).toContain("user_template: syntax");
  expect((screen.getByLabelText(/Prompt użytkownika/) as HTMLTextAreaElement).value).toBe("{{ zle");
});

it("previews the rendered prompt without saving", async () => {
  renderPage();
  await screen.findByDisplayValue("SYS");
  fireEvent.click(screen.getByRole("button", { name: /Podgląd/ }));
  await waitFor(() => expect(screen.getByText("RENDER")).toBeTruthy());
});

it("can load the built-in text into the editor", async () => {
  renderPage();
  await screen.findByDisplayValue("SYS");
  fireEvent.click(screen.getByRole("button", { name: "Wczytaj tekst wbudowany" }));
  expect(screen.getByDisplayValue("B-USER {{ catalog }}")).toBeTruthy();
});

it("edits the geopolitics prompt: asks for its own task, previews on a document and hides the topic comparison", async () => {
  const geoListing = {
    templates: [], variables: { fragment: "fragment dokumentu", countries: "slugi krajów" },
    builtin: { event_extraction: { system_template: null, user_template: "GEO {{ countries }} {{ fragment }}" } },
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/prompt_templates/preview")) return Promise.resolve(json({ system: null, user: "GEO RENDER", document_id: 11205 }));
    if (url.endsWith("/prompt_templates") && init?.method === "POST") {
      return Promise.resolve(json({ template: { ...template, id: 9, task: "geopolitics_events", variant: "event_extraction", version: 1, label: "event_extraction-v1" } }, 201));
    }
    if (url.includes("/prompt_templates?")) return Promise.resolve(json(geoListing));
    return Promise.reject(new TypeError("Failed to fetch"));
  }));
  render(<MemoryRouter initialEntries={["/prompt-templates?variant=event_extraction"]}><PromptTemplates /></MemoryRouter>);

  expect(await screen.findByDisplayValue("GEO {{ countries }} {{ fragment }}")).toBeTruthy();
  const listCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes("/prompt_templates?"));
  expect(String(listCall?.[0])).toContain("task=geopolitics_events");
  expect(String(listCall?.[0])).toContain("variant=event_extraction");
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/comparison"))).toBe(false);
  expect(screen.queryByText("Porównanie modeli i wersji promptu")).toBeNull();

  fireEvent.change(screen.getByLabelText("na dokumencie nr"), { target: { value: "11205" } });
  fireEvent.click(screen.getByRole("button", { name: "Podgląd (bez wywołania modelu)" }));
  expect(await screen.findByText("GEO RENDER")).toBeTruthy();
  expect(screen.getByText(/dokument 11205/)).toBeTruthy();
  const preview = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/preview"));
  expect(JSON.parse(String(preview?.[1]?.body))).toMatchObject({ task: "geopolitics_events", variant: "event_extraction", document_id: 11205 });

  fireEvent.click(screen.getByRole("button", { name: "Zapisz jako nową wersję i aktywuj" }));
  expect((await screen.findByRole("status")).textContent).toContain("event_extraction-v1");
  const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "POST" && String(init.body).includes("activate"));
  expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ task: "geopolitics_events", variant: "event_extraction", activate: true });
});
