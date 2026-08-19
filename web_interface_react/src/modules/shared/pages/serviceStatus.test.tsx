import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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

describe("ServiceStatus", () => {
  it("renders a service with a real observed timestamp without crashing", async () => {
    // Regression test: stamp() used to combine dateStyle/timeStyle with
    // timeZoneName in one Intl.DateTimeFormat call, which throws a
    // TypeError as soon as a real (non-null) timestamp reaches it --
    // an uncaught render exception that blanked the whole page.
    render(<AuthorizationContext.Provider value={auth}><ServiceStatus /></AuthorizationContext.Provider>);

    expect(await screen.findByText("CloudFerro Sherlock (LLM i embeddingi)")).toBeTruthy();
    expect(screen.getByText("Działa")).toBeTruthy();
    expect(screen.getByText(/4 udanych \/ 0 nieudanych/)).toBeTruthy();
  });
});
