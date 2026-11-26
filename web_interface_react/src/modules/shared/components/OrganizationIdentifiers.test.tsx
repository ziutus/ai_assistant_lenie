import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import OrganizationIdentifiers from "./OrganizationIdentifiers";

vi.mock("axios");
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const nip = { id: 1, country_code: "PL", identifier_type: "nip", value: "5260250995" };
const krs = { country_code: "PL", identifier_type: "krs", value: "0000000001", source_url: "https://example.org" };

// The organization page passes form-encoded headers, like this.
const pageHeaders = { "Content-Type": "application/x-www-form-urlencoded" };
const jsonHeaders = { headers: { "Content-Type": "application/json" } };

function show() {
  return render(<MemoryRouter><OrganizationIdentifiers organizationId={7} apiUrl="/api" headers={pageHeaders} /></MemoryRouter>);
}

it("loads identifiers, adds a custom type and confirms deletion inline", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { identifiers: [nip] } });
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  vi.mocked(axios.delete).mockResolvedValue({ data: {} });
  show();
  expect(await screen.findByText(/PL NIP: 5260250995/)).toBeTruthy();
  fireEvent.click(screen.getByText("Usuń"));
  expect(axios.delete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Anuluj"));
  expect(axios.delete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Usuń"));
  fireEvent.click(screen.getByText("Potwierdź usunięcie"));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/api/organizations/7/identifiers/1", { headers: pageHeaders }));
  await waitFor(() => expect((screen.getByText("Dodaj numer") as HTMLButtonElement).disabled).toBe(false));
  fireEvent.change(screen.getByLabelText("Kraj"), { target: { value: "MT" } });
  fireEvent.change(screen.getByLabelText("Typ numeru"), { target: { value: "other" } });
  fireEvent.change(screen.getByLabelText("Nazwa typu"), { target: { value: "company_number" } });
  fireEvent.change(screen.getByLabelText("Numer"), { target: { value: "C 123" } });
  fireEvent.click(screen.getByText("Dodaj numer"));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/api/organizations/7/identifiers",
    { country_code: "MT", identifier_type: "company_number", value: "C 123", source_url: "", note: "" }, jsonHeaders));
});

it("shows the owning organization and request URL on conflict", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { identifiers: [] } });
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 409, data: { message: "Numer jest już przypisany.",
    conflict_organization: { id: 42, canonical_name: "Inna firma" } } },
    config: { method: "post", url: "/api/organizations/7/identifiers" } });
  show();
  fireEvent.change(screen.getByLabelText("Numer"), { target: { value: "5260250995" } });
  fireEvent.click(screen.getByText("Dodaj numer"));
  expect((await screen.findByRole("alert")).textContent).toContain("Numer jest już przypisany.");
  expect(screen.getByRole("alert").textContent).toContain("/api/organizations/7/identifiers");
  expect(screen.getByRole("link", { name: "Inna firma" }).getAttribute("href")).toBe("/organizations/42");
});

it("checks stored numbers without retyping and saves a suggestion only on click", async () => {
  let added = false;
  vi.mocked(axios.get).mockImplementation(async url => ({ data: String(url).endsWith("/check") ? {
    warnings: [], crbr: { message: "Brak CRBR", filings: [] }, krs: { message: "Brak KRS" },
    vat: { status: "ok", message: "Pobrano VAT", subject: { name: "Firma VAT" } },
    ceidg: { status: "skipped", message: "Pominięto CEIDG" }, suggested_identifiers: [krs],
  } : { identifiers: added ? [nip, { ...krs, id: 2 }] : [nip] } }));
  vi.mocked(axios.post).mockImplementation(async () => { added = true; return { data: {} }; });
  show();
  await screen.findByText(/PL NIP/);
  fireEvent.click(screen.getByText("Rejestry (CRBR, KRS, VAT, CEIDG)"));
  fireEvent.click(screen.getByText("Sprawdź organizację"));
  expect(await screen.findByText("Firma VAT")).toBeTruthy();
  expect(screen.getByText("Pominięto CEIDG")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith("/api/company_registry/check", {
    headers: pageHeaders, params: { organization_id: 7 }, timeout: 180000,
  });
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Dodaj do organizacji"));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/api/organizations/7/identifiers", krs, jsonHeaders));
  expect(await screen.findByText(/PL KRS: 0000000001/)).toBeTruthy();
  expect(screen.queryByText("Dodaj do organizacji")).toBeNull();
});

it("says next to a suggestion that adding it failed", async () => {
  vi.mocked(axios.get).mockImplementation(async url => ({ data: String(url).endsWith("/check") ? {
    warnings: [], crbr: { message: "Brak CRBR", filings: [] }, krs: { message: "Brak KRS" }, suggested_identifiers: [krs],
  } : { identifiers: [nip] } }));
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 400, data: { message: "Zły numer." } },
    config: { method: "post", url: "/api/organizations/7/identifiers" } });
  show();
  await screen.findByText(/PL NIP/);
  fireEvent.click(screen.getByText("Rejestry (CRBR, KRS, VAT, CEIDG)"));
  fireEvent.click(screen.getByText("Sprawdź organizację"));
  fireEvent.click(await screen.findByText("Dodaj do organizacji"));
  expect(await screen.findByText(/Nie udało się dodać numeru\. Szczegóły/)).toBeTruthy();
});
