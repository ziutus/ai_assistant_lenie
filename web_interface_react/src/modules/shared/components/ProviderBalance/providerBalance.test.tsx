import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ProviderBalances, { ProviderBalanceView, type ProviderBalanceInfo } from "./providerBalance";

const cloudferro = (overrides: Partial<ProviderBalanceInfo> = {}): ProviderBalanceInfo => ({
  provider: "cloudferro", name: "CloudFerro", source: "estimated", unit: "BU", status: "ok", remaining: 18.5,
  days_left: 400, low: false, exhausted: false, base_amount: 18.98, as_of: "2026-11-02", spent_since: 0.48,
  fixed_monthly: 0, warn_days: 14, ...overrides,
});

describe("ProviderBalanceView", () => {
  afterEach(() => cleanup());

  it("shows the estimate with the runway", () => {
    render(<ProviderBalanceView balance={cloudferro()} />);
    const text = screen.getByRole("status").textContent ?? "";
    expect(text).toMatch(/CloudFerro: ok\. 18,50 BU \(szacunek\)/);
    expect(text).toContain("starczy na ok. 400 dni");
    expect(screen.getByRole("status").getAttribute("title")).toContain("Szacunek, nie dane dostawcy");
  });

  it("warns on a short runway and when the money is gone", () => {
    const { rerender } = render(<ProviderBalanceView balance={cloudferro({ days_left: 9, low: true })} />);
    expect(screen.getByRole("status").textContent).toContain("mniej niż 14 dni zapasu");
    rerender(<ProviderBalanceView balance={cloudferro({ remaining: -0.3, exhausted: true, days_left: 0 })} />);
    const text = screen.getByRole("status").textContent ?? "";
    expect(text).toMatch(/ok\. 0,00 BU/); // never negative
    expect(text).toContain("środki wyczerpane");
  });

  it("asks for a balance when none is set, and is honest about missing data", () => {
    const { container, rerender } = render(<ProviderBalanceView balance={cloudferro({ status: "not_configured", remaining: null })} />);
    expect(container.textContent).toContain("saldo nie ustawione");
    rerender(<ProviderBalanceView balance={null} />);
    expect(container.textContent).toContain("brak danych");
    rerender(<ProviderBalanceView balance={undefined} />);
    expect(container.textContent).toBe("");
  });
});

describe("ProviderBalances", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("lists only hand-entered balances and saves a new base with PUT", async () => {
    const openrouter: ProviderBalanceInfo = { ...cloudferro(), provider: "openrouter", name: "OpenRouter", source: "api", unit: "USD" };
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => ({
      ok: true, status: 200, json: async () => (init?.method === "PUT" ? { balance: cloudferro() } : { balances: [openrouter, cloudferro()] }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<ProviderBalances />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("CloudFerro"));
    expect(screen.queryByText(/OpenRouter/)).toBeNull();

    fireEvent.change(screen.getByLabelText("Saldo"), { target: { value: "12,5" } });
    fireEvent.click(screen.getByText("Zapisz saldo"));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/provider_balances/cloudferro") && init?.method === "PUT")).toBe(true));
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body)).amount).toBe(12.5);
  });

  it("shows 'no data' when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    render(<ProviderBalances />);
    await waitFor(() => expect(screen.getByText(/brak danych/)).toBeTruthy());
  });
});
