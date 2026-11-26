import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import axios from "axios";
import { afterEach, expect, it, vi } from "vitest";
import CompanyRegistryPanel from "./CompanyRegistryPanel";

vi.mock("axios");
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("fetches only on demand and shows warnings and source results", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: {
    warnings: [{ code: "hint", message: "Wpis może być nieaktualny." }],
    crbr: { status: "ok", message: "Pobrano CRBR.", filings: [{ reference: "1", is_current: true,
      presented_from: "2026-03-02", presented_to: "2026-11-26", beneficiaries: [
        { name: "Ada Testowa", ownership: [{ kind: "indirect", text: "60% Fikcyjna" }] }] }] },
    krs: { status: "ok", message: "Pobrano KRS.", current_shareholders: [{ name: "A****", shares: "50 udziałów" }],
      former_shareholders: [{ name: "Fikcyjna", shares: "50 udziałów", removed_at: "2026-09-30" }] },
  } });
  render(<CompanyRegistryPanel apiUrl="/api" headers={{ "x-api-key": "test" }} organizationId={7} />);
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /Sprawdź w rejestrach/ }));
  expect(await screen.findByText("Ada Testowa")).toBeTruthy();
  expect(screen.getByText("Wpis może być nieaktualny.")).toBeTruthy();
  expect(screen.getByText(/wykreślenie: 2026-09-30/)).toBeTruthy();
  expect(axios.post).toHaveBeenCalledWith("/api/organizations/7/identifiers/sync", {}, {
    headers: { "x-api-key": "test", "Content-Type": "application/json" }, timeout: 180000,
  });
});

it("shows a request failure with technical URL details", async () => {
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 400, data: { message: "Nieprawidłowy NIP." } },
    config: { method: "get", url: "/api/organizations/7/identifiers/sync" } });
  render(<CompanyRegistryPanel apiUrl="/api" headers={{}} organizationId={7} />);
  fireEvent.click(screen.getByRole("button", { name: /Sprawdź w rejestrach/ }));
  expect((await screen.findByRole("alert")).textContent).toContain("Nieprawidłowy NIP.");
  expect(screen.getByRole("alert").textContent).toContain("/api/organizations/7/identifiers/sync");
});
