import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import axios from "axios";
import { afterEach, expect, it, vi } from "vitest";
import CompanyRegistryPanel from "./CompanyRegistryPanel";

vi.mock("axios");
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("starts collapsed, fetches only on demand and shows warnings and source results", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: {
    warnings: [{ code: "hint", message: "Wpis może być nieaktualny." }],
    crbr: { status: "ok", message: "Pobrano CRBR.", filings: [{ reference: "1", is_current: true,
      presented_from: "2026-03-02", presented_to: "2026-11-26", beneficiaries: [
        { name: "Ada Testowa", ownership: [{ kind: "indirect", text: "60% Fikcyjna" }] }] }] },
    krs: { status: "ok", message: "Pobrano KRS.", current_shareholders: [{ name: "A****", shares: "50 udziałów" }],
      former_shareholders: [{ name: "Fikcyjna", shares: "50 udziałów", removed_at: "2026-09-30" }] },
  } });
  const { container } = render(<CompanyRegistryPanel apiUrl="/api" headers={{ "x-api-key": "test" }} />);
  expect(container.querySelector("details")?.open).toBe(false);
  expect(axios.get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Rejestry: CRBR i KRS"));
  fireEvent.change(screen.getByLabelText("Rodzaj identyfikatora"), { target: { value: "krs" } });
  fireEvent.change(screen.getByLabelText("Identyfikator"), { target: { value: "123" } });
  fireEvent.click(screen.getByText("Sprawdź"));
  expect(await screen.findByText("Ada Testowa")).toBeTruthy();
  expect(screen.getByText("Wpis może być nieaktualny.")).toBeTruthy();
  expect(screen.getByText(/wykreślenie: 2026-09-30/)).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith("/api/company_registry/check", {
    params: { krs: "123" }, headers: { "x-api-key": "test" }, timeout: 180000,
  });
});

it("shows a request failure with technical URL details", async () => {
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.get).mockRejectedValue({ response: { status: 400, data: { message: "Nieprawidłowy NIP." } },
    config: { method: "get", url: "/api/company_registry/check" } });
  render(<CompanyRegistryPanel apiUrl="/api" headers={{}} />);
  fireEvent.click(screen.getByText("Rejestry: CRBR i KRS"));
  fireEvent.change(screen.getByLabelText("Identyfikator"), { target: { value: "bad" } });
  fireEvent.click(screen.getByText("Sprawdź"));
  expect((await screen.findByRole("alert")).textContent).toContain("Nieprawidłowy NIP.");
  expect(screen.getByRole("alert").textContent).toContain("/api/company_registry/check");
});
