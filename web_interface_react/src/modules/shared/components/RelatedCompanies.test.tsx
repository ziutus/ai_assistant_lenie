import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import RelatedCompanies from "./RelatedCompanies";

vi.mock("axios");
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const headers = { "Content-Type": "application/x-www-form-urlencoded", "X-Test": "test" };
const row = { id: 4, organization_id: 1, subject_name: "Two", subject_krs: "0000000002", organization: null,
  name_candidates: [{ id: 2, canonical_name: "Two" }], details: "10 udziałów", valid_from: "2020-01-01",
  valid_to: "2022-01-01", source: "krs", source_url: "https://example.org/krs", checked_at: "2026-11-20T10:00:00" };
const empty = { shareholders: [], holdings: [] };
function component(refreshKey = 0) {
  return <MemoryRouter><RelatedCompanies organizationId={1} apiUrl="/api" headers={headers} refreshKey={refreshKey} /></MemoryRouter>;
}

it("hides empty data and refreshes after a registry check", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: empty });
  const view = render(component());
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));
  expect(screen.queryByText("Powiązane firmy")).toBeNull();
  vi.mocked(axios.get).mockResolvedValue({ data: { ...empty, shareholders: [row] } });
  view.rerender(component(1));
  expect(await screen.findByText("Powiązane firmy")).toBeTruthy();
  expect(screen.getByText(/Były wspólnik — do 2022-01-01/)).toBeTruthy();
  expect(screen.getByText("Sprawdź w Rejestrze firm").getAttribute("href")).toBe("/company-registry?krs=0000000002");
  expect(screen.getByText(/Sprawdzono:/)).toBeTruthy();
});

it("links a name candidate with JSON headers and confirms unlink inline", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { ...empty, shareholders: [row] } });
  vi.mocked(axios.patch).mockResolvedValue({ data: { ...empty, shareholders: [{ ...row,
    organization: { id: 2, canonical_name: "Two" } }] } });
  render(component());
  fireEvent.click(await screen.findByText("To ta firma"));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/api/organizations/1/relations/4",
    { related_organization_id: 2 }, { headers: { ...headers, "Content-Type": "application/json" } }));
  fireEvent.click(await screen.findByText("Odłącz"));
  expect(axios.patch).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText("Anuluj"));
  fireEvent.click(screen.getByText("Odłącz"));
  vi.mocked(axios.patch).mockResolvedValue({ data: empty });
  fireEvent.click(screen.getByText("Potwierdź odłączenie"));
  await waitFor(() => expect(axios.patch).toHaveBeenLastCalledWith("/api/organizations/1/relations/4",
    { related_organization_id: null }, { headers: { ...headers, "Content-Type": "application/json" } }));
});

it("searches arbitrary organizations and links the selected result", async () => {
  vi.mocked(axios.get).mockResolvedValueOnce({ data: { ...empty, shareholders: [row] } })
    .mockResolvedValueOnce({ data: { entries: [{ id: 3, canonical_name: "Three" }] } });
  vi.mocked(axios.patch).mockResolvedValue({ data: empty });
  render(component());
  fireEvent.change(await screen.findByLabelText("Szukaj organizacji"), { target: { value: "Three" } });
  fireEvent.click(screen.getByText("Szukaj"));
  fireEvent.change(await screen.findByLabelText("Wybierz firmę"), { target: { value: "3" } });
  fireEvent.click(screen.getByText("Powiąż"));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/api/organizations/1/relations/4",
    { related_organization_id: 3 }, expect.anything()));
  expect(axios.get).toHaveBeenCalledWith("/api/organizations", { params: { q: "Three" }, headers });
});

it("shows the holding company and request error details", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { shareholders: [], holdings: [{ ...row,
    organization: { id: 1, canonical_name: "One" }, holding_organization: { id: 3, canonical_name: "Three" } }] } });
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 500, data: { message: "Błąd zapisu." } },
    config: { method: "patch", url: "/api/organizations/1/relations/4" } });
  render(component());
  expect((await screen.findByText("Three")).getAttribute("href")).toBe("/organizations/3");
  fireEvent.click(screen.getByText("Odłącz"));
  fireEvent.click(screen.getByText("Potwierdź odłączenie"));
  expect((await screen.findByRole("alert")).textContent).toContain("Błąd zapisu.");
  expect(screen.getByRole("alert").textContent).toContain("/api/organizations/1/relations/4");
});
