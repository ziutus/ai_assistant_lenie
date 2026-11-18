import React from "react";
import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthorizationState } from "../../../types";
import { AuthorizationContext } from "../context/authorizationContext";
import ServiceStatus from "./serviceStatus";

const auth: AuthorizationState = {
  apiUrl: "http://api.test", apiKey: "service-key", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};

vi.mock("axios", () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      data: {
        observed_at: "2026-08-19T06:00:00Z",
        window_minutes: 15,
        services: [{
          id: "cloudferro", name: "CloudFerro Sherlock (LLM i embeddingi)", status: "ok", observed_only: true,
          successes: 4, failures: 0,
          last_success_at: "2026-08-19T05:58:12Z", last_failure_at: null,
          last_error_code: null, last_operation: "chat_completion",
        }],
      },
    }),
  },
}));

const BALANCES = [
  { provider: "firecrawl", name: "Firecrawl", source: "api", unit: "kredytów", status: "ok", remaining: 80, limit: 100, low: false, exhausted: false },
  { provider: "serper", name: "Serper", source: "api", unit: "kredytów", status: "not_configured" },
];

const renderPage = () => render(
  <MemoryRouter><AuthorizationContext.Provider value={auth}><ServiceStatus /></AuthorizationContext.Provider></MemoryRouter>,
);

describe("ServiceStatus", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ balances: BALANCES }) })));
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("renders a service with a real observed timestamp without crashing", async () => {
    // Regression test: stamp() used to combine dateStyle/timeStyle with
    // timeZoneName in one Intl.DateTimeFormat call, which throws a
    // TypeError as soon as a real (non-null) timestamp reaches it --
    // an uncaught render exception that blanked the whole page.
    renderPage();

    expect(await screen.findByText("CloudFerro Sherlock (LLM i embeddingi)")).toBeTruthy();
    expect(screen.getByText("Działa")).toBeTruthy();
    expect(screen.getByText(/4 udanych \/ 0 nieudanych/)).toBeTruthy();
  });

  it("shows how many credits are left of the paid services next to their health", async () => {
    renderPage();

    expect(await screen.findByText(/Firecrawl: zostało 80 kredytów z 100 kredytów/)).toBeTruthy();
    expect(screen.getByText(/Serper: brak klucza API/)).toBeTruthy();
    expect(screen.getByText("Salda i limity płatnych usług")).toBeTruthy();
  });

  it("requests the chosen time window, so days of proxy history can be inspected", async () => {
    renderPage();
    await screen.findByText("CloudFerro Sherlock (LLM i embeddingi)");

    fireEvent.change(screen.getByLabelText("Okno"), { target: { value: String(7 * 24 * 60) } });

    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith(
      "http://api.test/service_status",
      expect.objectContaining({ params: { window_minutes: 7 * 24 * 60 } }),
    ));
  });
});
