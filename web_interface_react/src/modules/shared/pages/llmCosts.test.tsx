import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import type { AuthorizationState } from "../../../types";
import { AuthorizationContext } from "../context/authorizationContext";
import LlmCosts from "./llmCosts";

vi.mock("axios");

const auth: AuthorizationState = {
  apiUrl: "http://api.test", apiKey: "user-key", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};

const report = {
  totals: [{ currency: "EUR", calls: 5, tokens: 1000, cost: "6.8", unknown_calls: 0 }],
  providers: [
    { provider: "cloudferro", currency: "EUR", calls: 5, tokens: 1000, cost: "6.8", unknown_calls: 0, failed_calls: 0 },
    { provider: "openrouter", currency: "USD", calls: 13, tokens: 12000, cost: "0.00131647", unknown_calls: 0, failed_calls: 0 },
    { provider: "openai", currency: null, calls: 3, tokens: 900, cost: null, unknown_calls: 3, failed_calls: 1 },
    { provider: "google-vertexai", currency: null, calls: 2, tokens: 500, cost: null, unknown_calls: 2, failed_calls: 0 },
  ],
  documents: [], daily: [], operations: [], analyses: [], calls: [],
};

const renderPage = () => render(
  <AuthorizationContext.Provider value={auth}><MemoryRouter><LlmCosts /></MemoryRouter></AuthorizationContext.Provider>,
);

describe("LlmCosts provider breakdown", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

  it("lists every provider with its own cost, currency, unpriced calls and errors", async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: report });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ balance: { status: "not_configured" } }) })));
    renderPage();

    const heading = await screen.findByText("Koszt per dostawca");
    const table = heading.nextElementSibling as HTMLElement;
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);

    const cell = (index: number, column: number) => within(rows[index]).getAllByRole("cell")[column].textContent ?? "";
    expect(cell(0, 0)).toContain("CloudFerro (Bielik)");
    expect(cell(0, 1)).toContain("EUR");
    expect(cell(1, 0)).toContain("OpenRouter");
    expect(cell(1, 1)).toContain("USD");
    expect(cell(2, 0)).toContain("OpenAI");
    expect(cell(2, 1)).toBe("—");
    expect(cell(2, 4)).toContain("3 bez ceny");
    expect(cell(2, 5)).toBe("1");
    expect(cell(3, 0)).toContain("Google (Vertex AI, Gemini)");
  });

  it("shows the OpenRouter key balance above the report", async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: report });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ balance: { status: "ok", has_limit: true, limit_usd: 3, remaining_usd: 2.87, usage_usd: 0.13, reset: "monthly", low: false, exhausted: false } }),
    })));
    renderPage();
    expect((await screen.findByText(/OpenRouter: zostało/)).textContent).toMatch(/2,87 USD z 3,00 USD/);
  });

  it("works with a report from an older backend that has no providers", async () => {
    const { providers, ...older } = report;
    void providers;
    vi.mocked(axios.get).mockResolvedValue({ data: older });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ balance: { status: "not_configured" } }) })));
    renderPage();
    await screen.findByText("Podsumowanie");
    expect(screen.queryByText("Koszt per dostawca")).toBeNull();
  });
});

describe("LLM call payload", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.resetAllMocks(); });
  const call = { id: 42, document_id: 12, called_at: "2026-11-06T12:00:00Z", operation: "country_tagging", provider: "openai", model: "model", cost_status: "known", success: true, has_payload: true };
  function setup(payload: unknown = { request_text: "Zapytanie testowe", response_text: "Odpowiedź testowa", system_prompt: "System testowy", request_extra: { temperature: 0 }, request_truncated: true, error: "Błąd modelu" }, fail = false) {
    vi.mocked(axios.get).mockImplementation(async (url) => {
      if (String(url).endsWith("/payload")) {
        if (fail) throw { response: { status: 404 }, config: { method: "get", url } };
        return { data: { payload } };
      }
      return { data: { ...report, calls: [call, { ...call, id: 43, has_payload: false }, { ...call, id: 44, has_payload: undefined }] } };
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ balance: { status: "not_configured" } }) })));
    return render(<AuthorizationContext.Provider value={auth}><MemoryRouter initialEntries={["/llm-costs?document_id=12"]}><LlmCosts /></MemoryRouter></AuthorizationContext.Provider>);
  }
  it("offers preview only for saved payloads and fetches lazily with truncation and JSON", async () => {
    setup();
    const button = await screen.findByRole("button", { name: "Podgląd" });
    expect(screen.getAllByText(/Brak zapisanej treści tego wywołania/)).toHaveLength(2);
    expect(vi.mocked(axios.get).mock.calls.some(([url]) => String(url).includes("/payload"))).toBe(false);
    fireEvent.click(button);
    expect(await screen.findByText("Zapis obcięty (limit pola)")).toBeTruthy();
    expect(screen.getByText("Zapytanie testowe")).toBeTruthy();
    expect(screen.getByText("Odpowiedź testowa")).toBeTruthy();
    expect(screen.getByText("System testowy")).toBeTruthy();
    expect(screen.getByText(/"temperature": 0/)).toBeTruthy();
    expect(screen.getByText("Błąd modelu")).toBeTruthy();
    expect(axios.get).toHaveBeenCalledWith("http://api.test/llm_usage/42/payload", { headers: { "x-api-key": "user-key" } });
    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByText("Zapis obcięty (limit pola)")).toBeNull());
  });
  it("handles payload removed by retention", async () => {
    setup(null); fireEvent.click(await screen.findByRole("button", { name: "Podgląd" }));
    await waitFor(() => expect(screen.getAllByText(/Brak zapisanej treści tego wywołania/)).toHaveLength(3));
  });
  it("shows request error and target URL", async () => {
    setup(null, true); fireEvent.click(await screen.findByRole("button", { name: "Podgląd" }));
    expect(await screen.findByText(/Nie udało się pobrać treści wywołania LLM:/, { selector: "p" })).toBeTruthy();
    expect(screen.getByText(/Żądanie: GET.*llm_usage\/42\/payload/)).toBeTruthy();
  });
});
