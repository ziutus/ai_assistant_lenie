import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import axios from "axios";
import { afterEach, expect, it, vi } from "vitest";
import CompanyRegistry from "./companyRegistry";
import { AuthorizationContext } from "../context/authorizationContext";
import { probeBackend } from "../utils/backendProbe";

vi.mock("axios");
vi.mock("../utils/backendProbe", () => ({ probeBackend: vi.fn().mockResolvedValue(["Backend działa"]) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const base = {
  warnings: [], crbr: { status: "ok", message: "Pobrano CRBR", filings: [] },
  krs: { status: "ok", message: "Pobrano KRS" },
  lenie_match: {
    owners: [] as { id: number; canonical_name: string }[],
    name_candidates: [] as { id: number; canonical_name: string }[],
    identifiers: [{ country_code: "PL", identifier_type: "nip", value: "5260250995", source_url: "https://example.org" }],
    disagreeing: [], registry_name: "INVICTI SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ",
    suggested_name: "Invicti", sole_proprietor: false,
  },
};

function Location() { return <output aria-label="URL">{useLocation().search}</output>; }
function View() {
  const context = React.useContext(AuthorizationContext);
  return <AuthorizationContext.Provider value={{ ...context, apiKey: "test", apiUrl: "/api" }}>
    <CompanyRegistry /><Location />
  </AuthorizationContext.Provider>;
}
function setup(match = {}, url = "/company-registry?nip=5260250995") {
  vi.mocked(axios.get).mockResolvedValue({ data: { ...base, lenie_match: { ...base.lenie_match, ...match } } });
  return render(<React.StrictMode><MemoryRouter initialEntries={[url]}><View /></MemoryRouter></React.StrictMode>);
}

it("runs the URL query once, shows owners and never offers creation", async () => {
  setup({ owners: [{ id: 7, canonical_name: "Istniejąca" }] });
  expect(await screen.findByText(/Ten numer ma już organizacja/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Istniejąca" }).getAttribute("href")).toBe("/organizations/7");
  expect(screen.queryByText("Dodaj organizację")).toBeNull();
  expect(axios.get).toHaveBeenCalledTimes(1);
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.get).toHaveBeenCalledWith("/api/company_registry/check", expect.objectContaining({
    params: { nip: "5260250995", match: "1" },
  }));
});

it("offers name candidates and attaches only after a click with JSON headers", async () => {
  setup({ name_candidates: [{ id: 9, canonical_name: "Invicti" }] });
  const attach = await screen.findByText("Przypisz numery do tej organizacji");
  expect(screen.getByText("To inna firma, utwórz nową")).toBeTruthy();
  expect(axios.post).not.toHaveBeenCalled();
  vi.mocked(axios.post).mockResolvedValue({ data: { organization: { id: 9, canonical_name: "Invicti" }, warnings: [] } });
  fireEvent.click(attach);
  await screen.findByText(/Zapisano organizację/);
  expect(axios.post).toHaveBeenCalledWith("/api/company_registry/organizations", {
    nip: "5260250995", organization_id: 9, confirm_sole_proprietor: false,
  }, { headers: { "x-api-key": "test", "Content-Type": "application/json" }, timeout: 180000 });
});

it("opens an editable create form and displays the saved link and alias warning", async () => {
  setup();
  fireEvent.click(await screen.findByText("Dodaj organizację"));
  expect((screen.getByLabelText("Nazwa organizacji") as HTMLInputElement).value).toBe("Invicti");
  expect(screen.getByText(/Pełna nazwa jako alias:/).textContent).toContain(base.lenie_match.registry_name);
  expect(screen.getByText(/Numery do zapisania:/).textContent).toContain("5260250995");
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Nazwa organizacji"), { target: { value: "Moja nazwa" } });
  vi.mocked(axios.post).mockResolvedValue({ data: {
    organization: { id: 12, canonical_name: "Moja nazwa" }, warnings: ["Alias zajęty"],
  } });
  fireEvent.click(screen.getByText("Zapisz organizację"));
  expect(await screen.findByText("Alias zajęty")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Moja nazwa" }).getAttribute("href")).toBe("/organizations/12");
  expect(axios.post).toHaveBeenCalledWith("/api/company_registry/organizations", {
    nip: "5260250995", canonical_name: "Moja nazwa", confirm_sole_proprietor: false,
  }, expect.objectContaining({ headers: { "x-api-key": "test", "Content-Type": "application/json" } }));
});

it("requires explicit sole proprietor confirmation for both creation and attachment", async () => {
  setup({ sole_proprietor: true, name_candidates: [{ id: 9, canonical_name: "Invicti" }] });
  const attach = await screen.findByText("Przypisz numery do tej organizacji") as HTMLButtonElement;
  expect(attach.disabled).toBe(true);
  fireEvent.click(screen.getByText("To inna firma, utwórz nową"));
  expect((screen.getByText("Zapisz organizację") as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox"));
  expect(attach.disabled).toBe(false);
  vi.mocked(axios.post).mockResolvedValue({ data: { organization: { id: 12, canonical_name: "Invicti" }, warnings: [] } });
  fireEvent.click(screen.getByText("Zapisz organizację"));
  await screen.findByText(/Zapisano organizację/);
  expect(vi.mocked(axios.post).mock.calls[0][1]).toMatchObject({ confirm_sole_proprietor: true });
});

it("writes the form query to the URL and runs it once", async () => {
  setup({}, "/company-registry");
  expect(axios.get).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Rodzaj identyfikatora"), { target: { value: "krs" } });
  fireEvent.change(screen.getByLabelText("Numer"), { target: { value: "123" } });
  fireEvent.click(screen.getByText("Sprawdź"));
  await screen.findByText("Dodaj organizację");
  expect(screen.getByLabelText("URL").textContent).toBe("?krs=123");
  expect(axios.get).toHaveBeenCalledTimes(1);
  expect(axios.get).toHaveBeenCalledWith("/api/company_registry/check", expect.objectContaining({ params: { krs: "123", match: "1" } }));
});

it("shows fixed server error and the failed target URL on save", async () => {
  setup();
  fireEvent.click(await screen.findByText("Dodaj organizację"));
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.post).mockRejectedValue({ response: { status: 409, data: { message: "Numer już zajęty." } },
    config: { method: "post", url: "/api/company_registry/organizations" } });
  fireEvent.click(screen.getByText("Zapisz organizację"));
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Numer już zajęty.");
  expect(alert.textContent).toContain("/api/company_registry/organizations");
});

it("probes the backend when a lookup receives no response", async () => {
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  setup({}, "/company-registry");
  vi.mocked(axios.get).mockRejectedValue({ code: "ERR_NETWORK", config: { url: "/api/company_registry/check" } });
  fireEvent.change(screen.getByLabelText("Numer"), { target: { value: "123" } });
  fireEvent.click(screen.getByText("Sprawdź"));
  await waitFor(() => expect(probeBackend).toHaveBeenCalledWith("/api"));
  expect((await screen.findByRole("alert")).textContent).toContain("/api/company_registry/check");
});
