import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import OpenRouterBalance, { OpenRouterBalanceView, type OpenRouterBalanceInfo } from "./openRouterBalance";

const balance = (overrides: Partial<OpenRouterBalanceInfo> = {}): OpenRouterBalanceInfo => ({
  status: "ok", has_limit: true, limit_usd: 3, remaining_usd: 2.87, usage_usd: 0.13, reset: "monthly",
  free_tier: false, low: false, exhausted: false, ...overrides,
});

describe("OpenRouterBalanceView", () => {
  afterEach(() => cleanup());

  it("shows what is left of the key's limit", () => {
    render(<OpenRouterBalanceView balance={balance()} />);
    const text = screen.getByRole("status").textContent ?? "";
    expect(text).toContain("zostało");
    expect(text).toMatch(/2,87 USD z 3,00 USD/);
    expect(text).toContain("limit miesięczny");
    expect(text).not.toContain("na wyczerpaniu");
  });

  it("warns when the money runs low and when it is used up", () => {
    const { rerender } = render(<OpenRouterBalanceView balance={balance({ remaining_usd: 0.4, low: true })} />);
    expect(screen.getByRole("status").textContent).toContain("środki na wyczerpaniu");
    rerender(<OpenRouterBalanceView balance={balance({ remaining_usd: -0.01, low: true, exhausted: true })} />);
    const text = screen.getByRole("status").textContent ?? "";
    expect(text).toContain("limit wyczerpany");
    expect(text).toMatch(/zostało 0,00 USD/); // never a negative balance
  });

  it("shows small amounts with enough digits", () => {
    render(<OpenRouterBalanceView balance={balance({ limit_usd: 0.5, remaining_usd: 0.0987 })} />);
    expect(screen.getByRole("status").textContent).toMatch(/0,0987 USD z 0,50 USD/);
  });

  it("asks for a limit when the key has none, and still shows the usage", () => {
    render(<OpenRouterBalanceView balance={balance({ has_limit: false, limit_usd: null, remaining_usd: null, usage_usd: 1.5 })} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("klucz bez limitu");
    expect(status.textContent).toMatch(/zużyto 1,50 USD/);
    expect(status.getAttribute("title")).toContain("Ustaw limit klucza");
  });

  it("is honest about missing data and stays silent before loading or without OpenRouter", () => {
    const { container, rerender } = render(<OpenRouterBalanceView balance={undefined} />);
    expect(container.textContent).toBe("");
    rerender(<OpenRouterBalanceView balance={{ status: "not_configured" }} />);
    expect(container.textContent).toBe("");
    rerender(<OpenRouterBalanceView balance={{ status: "unavailable" }} />);
    expect(container.textContent).toContain("brak danych o saldzie");
    rerender(<OpenRouterBalanceView balance={null} />);
    expect(container.textContent).toContain("brak danych o saldzie");
  });
});

describe("OpenRouterBalance", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("loads the balance and reloads when the refresh key changes", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ balance: balance() }) }));
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<OpenRouterBalance refreshKey={0} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("zostało"));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    rerender(<OpenRouterBalance refreshKey={1} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("shows 'no data' when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    render(<OpenRouterBalance />);
    await waitFor(() => expect(screen.getByText(/brak danych o saldzie/)).toBeTruthy());
  });
});
