import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Tools from "./tools";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://api", apiKey: "test-key" }) };
});

const baseTool = {
  id: 1, uuid: "u-1", name: "Terraform", category_tags: ["iac"], homepage_url: "https://terraform.io",
  license: "MPL-2.0", pricing: null, github_url: "https://github.com/hashicorp/terraform", wikipedia_url: null,
  pricing_url: null, pricing_type: "open_core", app_type: "CLI", migrating_away: false, migration_note: null, migration_target: null,
  github: {
    full_name: "hashicorp/terraform", status: "ok", stars: 40000, forks: 9000, watchers: 1000, open_issues: 2000,
    language: "Go", license: "BUSL-1.1", archived: false, pushed_at: new Date().toISOString(), fetched_at: "2026-10-23T10:00:00Z",
  },
  personal_notes: null, source_document_id: null, source_candidate_id: null, status: "accepted", obsidian_note_path: null,
  relations: [], created_at: null, updated_at: null,
};
const obsidian = {
  ...baseTool, id: 2, name: "Obsidian", category_tags: [], github_url: null, github: null, pricing_type: "freemium",
  app_type: "notatnik", license: null,
  migrating_away: true, migration_note: "przechodzę na Lenie",
};

const renderTools = (path = "/tools") =>
  render(<MemoryRouter initialEntries={[path]}><Tools /></MemoryRouter>);

const jsonResponse = (body: unknown, ok = true) =>
  ({ ok, status: ok ? 200 : 400, text: async () => JSON.stringify(body), json: async () => body }) as unknown as Response;

beforeEach(() => vi.resetAllMocks());
afterEach(() => cleanup());

it("shows the catalog fields, GitHub numbers and the migrating-away flag", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ tools: [baseTool, obsidian] })));
  renderTools();

  expect(await screen.findByText("Terraform")).toBeTruthy();
  expect(screen.getAllByText("Typ").length).toBe(2); // one facts grid per tool
  expect(screen.getByText("CLI")).toBeTruthy();
  expect(screen.getByLabelText("gwiazdki").textContent).toContain("40");
  expect(screen.queryByText("Ważne polecenia")).toBeNull();
  expect(screen.getAllByText("Model cenowy").length).toBe(2);
  expect(screen.getByText("open core")).toBeTruthy();
  expect(screen.getByText("odchodzę")).toBeTruthy();
  expect(screen.getByText("przechodzę na Lenie")).toBeTruthy();
});

it("filters to the tools being phased out", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ tools: [baseTool, obsidian] })));
  renderTools();
  await screen.findByText("Terraform");

  fireEvent.click(screen.getByLabelText("Tylko te, z których odchodzę"));

  expect(screen.queryByText("Terraform")).toBeNull();
  expect(screen.getByText("Obsidian")).toBeTruthy();
});

it("saves the edited details without key points or commands", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ tools: [baseTool] }))
    .mockResolvedValueOnce(jsonResponse({ tool: { ...baseTool, migrating_away: true } }));
  vi.stubGlobal("fetch", fetchMock);
  renderTools();
  await screen.findByText("Terraform");

  fireEvent.click(screen.getByRole("button", { name: "Edytuj dane" }));
  expect(screen.queryByLabelText(/Najważniejsze punkty|Ważne polecenia/)).toBeNull();
  fireEvent.click(screen.getByLabelText("Odchodzę od tego narzędzia"));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz dane" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
  expect(url).toBe("http://api/tools/1");
  expect(init.method).toBe("PATCH");
  const body = JSON.parse(String(init.body));
  expect(body).not.toHaveProperty("key_points");
  expect(body).not.toHaveProperty("important_commands");
  expect(body.migrating_away).toBe(true);
  expect(body.pricing_type).toBe("open_core");
  expect(await screen.findByText("odchodzę")).toBeTruthy();
});

it("shows one tool with its links and steps between tools with previous/next", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ tools: [baseTool, obsidian] })));
  vi.stubGlobal("scrollTo", vi.fn());
  renderTools("/tools?tool=1");

  expect(await screen.findByText("Linki")).toBeTruthy();
  expect(screen.getByText("1 / 2")).toBeTruthy();
  expect(screen.getByText("GitHub:")).toBeTruthy();
  expect(screen.queryByText("Obsidian")).toBeNull();
  expect((screen.getByRole("button", { name: "← Poprzednie" }) as HTMLButtonElement).disabled).toBe(true);

  fireEvent.click(screen.getByRole("button", { name: "Następne →" }));
  expect(await screen.findByText("Obsidian")).toBeTruthy();
  expect(screen.getByText("2 / 2")).toBeTruthy();
  expect(screen.queryByText("Terraform")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "← Wszystkie narzędzia" }));
  expect(await screen.findByText("Terraform")).toBeTruthy();
  expect(screen.getByText("Obsidian")).toBeTruthy();
});

it("lets you pick the tool you migrate to, only while migrating away is ticked", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ tools: [baseTool, obsidian] }))
    .mockResolvedValueOnce(jsonResponse({ tool: { ...obsidian, migration_target: { id: 1, name: "Terraform" } } }));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("scrollTo", vi.fn());
  renderTools("/tools?tool=2");
  await screen.findByText("Obsidian");

  fireEvent.click(screen.getByRole("button", { name: "Edytuj dane" }));
  fireEvent.click(screen.getByLabelText("Odchodzę od tego narzędzia")); // untick: the target field disappears
  expect(screen.queryByLabelText(/Na jakie narzędzie przechodzę/)).toBeNull();
  fireEvent.click(screen.getByLabelText("Odchodzę od tego narzędzia"));
  fireEvent.change(screen.getByLabelText(/Na jakie narzędzie przechodzę/), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz dane" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
  expect(url).toBe("http://api/tools/2");
  expect(JSON.parse(String(init.body)).migration_target_tool_id).toBe(1);
  expect(await screen.findByText("Przechodzę na:")).toBeTruthy();
});

const withOrigin = {
  ...baseTool,
  sources: [{ id: 5, name: "Akademia Bezpiecznego Kodu", kind: "course", url: null, status: "finished", rating: 4, context: null }],
  radar: [{
    id: 9, status: "adopted", source_context: "Zbudowaliśmy audytora NDA", source_url: null, created_at: null,
    source_document: { id: 9381, title: "Newsletter AI Flash", url: "gmail://x", discovery_source: "newsletter:AI Flash" },
    evidence_count: 1, evidences: [],
  }],
};

it("lists the extra links next to the named ones and saves them as {url, label}", async () => {
  const withLinks = {
    ...baseTool, github: null,
    links: [{ url: "https://hub.docker.com/r/x/terraform", label: "Docker Hub" }, { url: "https://terraform.io", label: "duplikat" }],
  };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ tools: [withLinks] }))
    .mockResolvedValueOnce(jsonResponse({ tool: withLinks }));
  vi.stubGlobal("fetch", fetchMock);
  renderTools();

  const dockerHub = await screen.findByRole("link", { name: "Docker Hub" });
  expect((dockerHub as HTMLAnchorElement).href).toBe("https://hub.docker.com/r/x/terraform");
  expect(screen.queryByRole("link", { name: "duplikat" })).toBeNull(); // the homepage already has that address

  fireEvent.click(screen.getByRole("button", { name: "Edytuj dane" }));
  fireEvent.change(screen.getByLabelText(/Dodatkowe linki/), { target: { value: "Docs | https://docs.example.com\nhttps://bare.example.com" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz dane" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const body = JSON.parse(String((fetchMock.mock.calls[1] as [string, RequestInit])[1].body));
  expect(body.links).toEqual([{ label: "Docs", url: "https://docs.example.com" }, { label: "", url: "https://bare.example.com" }]);
});

it("shows where the tool is known from and why it was on the radar", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ tools: [withOrigin] })));
  renderTools();

  expect(await screen.findByText("Akademia Bezpiecznego Kodu")).toBeTruthy();
  expect(screen.getByText(/Zbudowaliśmy audytora NDA/)).toBeTruthy();
  expect(screen.getByText("Newsletter AI Flash")).toBeTruthy();
  expect(screen.getByText(/newsletter:AI Flash/)).toBeTruthy();
});

it("adds a source by name and removes one", async () => {
  const added = [...withOrigin.sources, { id: 6, name: "Kurs X", kind: "course", url: null, status: null, rating: null, context: null }];
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ tools: [withOrigin] }))
    .mockResolvedValueOnce(jsonResponse({ sources: [{ id: 5, name: "Akademia Bezpiecznego Kodu", is_active: true }] }))
    .mockResolvedValueOnce(jsonResponse({ sources: added, source_created: true, linked: true }))
    .mockResolvedValueOnce(jsonResponse({ sources: [added[1]] }));
  vi.stubGlobal("fetch", fetchMock);
  renderTools();
  await screen.findByText("Akademia Bezpiecznego Kodu");

  fireEvent.click(screen.getByRole("button", { name: "+ źródło" }));
  fireEvent.change(screen.getByPlaceholderText(/nazwa kursu/), { target: { value: "Kurs X" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));

  expect(await screen.findByText("Kurs X")).toBeTruthy();
  const [url, init] = fetchMock.mock.calls[2] as [string, RequestInit];
  expect(url).toBe("http://api/tools/1/sources");
  expect(JSON.parse(String(init.body))).toEqual({ name: "Kurs X" });

  fireEvent.click(screen.getByRole("button", { name: "Usuń źródło Akademia Bezpiecznego Kodu" }));
  await waitFor(() => expect(screen.queryByText("Akademia Bezpiecznego Kodu")).toBeNull());
  expect((fetchMock.mock.calls[3] as [string, RequestInit])[1].method).toBe("DELETE");
});
