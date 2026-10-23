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
  pricing_url: null, pricing_type: "open_core", app_type: "CLI", key_points: ["plan/apply"],
  important_commands: "terraform plan", migrating_away: false, migration_note: null,
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
  key_points: [], important_commands: null, migrating_away: true, migration_note: "przechodzę na Lenie",
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
  expect(screen.getByText("Typ: CLI")).toBeTruthy();
  expect(screen.getByLabelText("gwiazdki").textContent).toContain("40");
  expect(screen.getByText("plan/apply")).toBeTruthy();
  expect(screen.getByText("Model: open core")).toBeTruthy();
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

it("saves the edited details with key points as a list", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ tools: [baseTool] }))
    .mockResolvedValueOnce(jsonResponse({ tool: { ...baseTool, migrating_away: true, key_points: ["a", "b"] } }));
  vi.stubGlobal("fetch", fetchMock);
  renderTools();
  await screen.findByText("Terraform");

  fireEvent.click(screen.getByRole("button", { name: "Edytuj dane" }));
  fireEvent.change(screen.getByLabelText(/Najważniejsze punkty/), { target: { value: "a\n\n b " } });
  fireEvent.click(screen.getByLabelText("Odchodzę od tego narzędzia"));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz dane" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
  expect(url).toBe("http://api/tools/1");
  expect(init.method).toBe("PATCH");
  const body = JSON.parse(String(init.body));
  expect(body.key_points).toEqual(["a", "b"]);
  expect(body.migrating_away).toBe(true);
  expect(body.pricing_type).toBe("open_core");
  expect(await screen.findByText("odchodzę")).toBeTruthy();
});

it("shows one tool with its links and steps between tools with previous/next", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ tools: [baseTool, obsidian] })));
  vi.stubGlobal("scrollTo", vi.fn());
  renderTools("/tools?tool=1");

  expect(await screen.findByText("Linki i źródła")).toBeTruthy();
  expect(screen.getByText("1 / 2")).toBeTruthy();
  expect(screen.getByText("Repozytorium GitHub:")).toBeTruthy();
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
