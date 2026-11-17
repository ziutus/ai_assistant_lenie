import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import TranscriptCorrectionsTable, { type CorrectionRule } from "./transcriptCorrectionsTable";

vi.mock("axios");
vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const rule = (overrides: Partial<CorrectionRule>): CorrectionRule => ({
  id: 1, pattern: "Tais", replacement: "Taiz", scope: "region", author: null, country_slug: "kraj-jemen", active: true,
  note: "miasto", created_by: "seed", hit_count: 15, last_hit_at: "2026-11-17T08:00:00", ...overrides,
});

const rules = [rule({}), rule({ id: 2, pattern: "huti", replacement: "Huti", note: null, active: false, hit_count: 0, last_hit_at: null })];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data: { status: "success", rules, total: 2 } });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.patch).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.delete).mockResolvedValue({ data: { status: "success" } });
});
afterEach(cleanup);

const open = (mode: "region" | "phrases" = "region", url = "/dictionaries?tab=region") => render(
  <MemoryRouter initialEntries={[url]}><TranscriptCorrectionsTable mode={mode} /></MemoryRouter>);

it("lists region rules with scope, usage and an inactive rule dimmed", async () => {
  open();
  const table = await screen.findByRole("table");
  expect(within(table).getByText("Taiz")).toBeTruthy();
  expect(within(table).getAllByText("region kraj-jemen")).toHaveLength(2);
  expect(within(table).getByText("×15")).toBeTruthy();
  expect(vi.mocked(axios.get).mock.calls[0][1]?.params).toEqual({ scope: "region", limit: 50, offset: 0 });
});

it("asks for global and channel rules on the phrases tab", async () => {
  open("phrases", "/dictionaries?tab=phrases");
  await screen.findByRole("table");
  expect(vi.mocked(axios.get).mock.calls[0][1]?.params).toMatchObject({ scope: "global,author" });
});

it("adds a one-word region rule with the country tag", async () => {
  open();
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Region"), { target: { value: "kraj-jemen" } });
  fireEvent.change(screen.getByLabelText("Wzorzec"), { target: { value: "Marip" } });
  fireEvent.change(screen.getByLabelText("Poprawna wersja"), { target: { value: "Marib" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/transcript_corrections", {
    pattern: "Marip", replacement: "Marib", scope: "region", note: null, country_slug: "kraj-jemen",
  }, expect.any(Object)));
  expect(await screen.findByText(/Dodano regułę „Marip”/)).toBeTruthy();
});

it("requires a channel for a channel phrase rule and sends it otherwise", async () => {
  open("phrases", "/dictionaries?tab=phrases");
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Zakres reguły"), { target: { value: "author" } });
  fireEvent.change(screen.getByLabelText("Wzorzec"), { target: { value: "pięto Achillesa" } });
  fireEvent.change(screen.getByLabelText("Poprawna wersja"), { target: { value: "pięta Achillesa" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  expect((await screen.findByRole("alert")).textContent).toContain("podaj kanał");
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Kanał"), { target: { value: "Na Wschód od Bliskiego Wschodu" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/transcript_corrections", expect.objectContaining({
    scope: "author", author: "Na Wschód od Bliskiego Wschodu",
  }), expect.any(Object)));
});

it("switches a rule off, edits its replacement and deletes it in two steps", async () => {
  open();
  await screen.findByRole("table");
  fireEvent.click(screen.getByLabelText("Aktywna Tais"));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/transcript_corrections/1", { active: false }, expect.any(Object)));

  fireEvent.click(screen.getAllByRole("button", { name: "Edytuj" })[0]);
  fireEvent.change(screen.getByLabelText("Poprawka Tais"), { target: { value: "Ta'izz" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/transcript_corrections/1",
    { replacement: "Ta'izz", note: "miasto" }, expect.any(Object)));

  fireEvent.click(screen.getAllByRole("button", { name: "Usuń" })[0]);
  expect(axios.delete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Potwierdź usunięcie" }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/transcript_corrections/1", expect.any(Object)));
});

it("explains a 403 on edit as a service-key requirement", async () => {
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 403, data: { message: "Zapis reguł wymaga klucza service" } } });
  open();
  await screen.findByRole("table");
  fireEvent.click(screen.getByLabelText("Aktywna Tais"));
  expect((await screen.findByRole("alert")).textContent).toContain("klucza service");
});

it("paginates from the URL (page 2 asks for offset 50)", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { status: "success", rules, total: 120 } });
  open("region", "/dictionaries?tab=region&page=2");
  await screen.findByRole("table");
  expect(vi.mocked(axios.get).mock.calls[0][1]?.params).toMatchObject({ limit: 50, offset: 50 });
  expect(screen.getByRole("navigation", { name: "Stronicowanie reguł słownika" })).toBeTruthy();
});
