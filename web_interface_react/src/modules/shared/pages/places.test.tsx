import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Places from "./places";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const profile = { id: 1, canonical_name: "Yanbu", wikipedia_url: "https://en.wikipedia.org/wiki/Yanbu", aliases: ["Janbu"], note: null };
const rows = [
  { key: "janbu", name: "Janbu", documents: 2, mentions: 9, located: true, is_country: false, profile },
  { key: "polska", name: "Polska", documents: 5, mentions: 40, located: false, is_country: true, profile: null },
];
const detail = {
  name: "Yanbu", profile,
  documents: [{ id: 10872, title: "Film o ropie", document_type: "youtube", mentions: 8, forms: ["Janb", "Janbu"] }],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url: string) => (
    url.endsWith("/places/detail") ? { data: detail } : { data: { places: rows, total: 2 } }));
  vi.mocked(axios.put).mockResolvedValue({ data: { status: "success" } });
});
afterEach(cleanup);

const open = (url = "/places") => render(<MemoryRouter initialEntries={[url]}><Routes><Route path="/places" element={<Places />} /></Routes></MemoryRouter>);

it("lists places across documents with their Wikipedia link", async () => {
  open();
  const table = await screen.findByRole("table");
  expect(within(table).getByRole("button", { name: "Janbu" })).toBeTruthy();
  expect(within(table).getByRole("link", { name: "Wikipedia: Janbu" }).getAttribute("href")).toBe("https://en.wikipedia.org/wiki/Yanbu");
  expect(within(table).getByTitle("Państwo")).toBeTruthy();
  expect(vi.mocked(axios.get)).toHaveBeenCalledWith("/places", expect.objectContaining({
    params: { q: "", with_wikipedia: "0", limit: 50, offset: 0 } }));
});

it("filters by name and by having a Wikipedia article through the URL", async () => {
  open("/places?q=jan&with_wikipedia=1");
  await screen.findByRole("table");
  expect(vi.mocked(axios.get)).toHaveBeenCalledWith("/places", expect.objectContaining({
    params: { q: "jan", with_wikipedia: "1", limit: 50, offset: 0 } }));
  expect((screen.getByRole("checkbox", { name: "Tylko z Wikipedią" }) as HTMLInputElement).checked).toBe(true);
});

it("shows the documents linked to a place and saves the profile", async () => {
  open("/places?name=Janbu");
  const details = await screen.findByRole("complementary", { name: "Szczegóły miejsca" });
  expect(await within(details).findByRole("link", { name: "Film o ropie" })).toBeTruthy();
  expect(within(details).getByText(/youtube · ×8 \(Janb, Janbu\)/)).toBeTruthy();
  expect((within(details).getByLabelText("Aliasy (po przecinku)") as HTMLInputElement).value).toBe("Janbu");
  fireEvent.change(within(details).getByLabelText("Aliasy (po przecinku)"), { target: { value: "Janbu, Yenbo" } });
  fireEvent.click(within(details).getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith("/places/profile", {
    name: "Yanbu", wikipedia_url: "https://en.wikipedia.org/wiki/Yanbu", aliases: ["Janbu", "Yenbo"], note: null,
  }, { headers: { "x-api-key": "test-key" } }));
  expect(await within(details).findByText("Zapisano.")).toBeTruthy();
});

it("reports a rejected Wikipedia address", async () => {
  vi.mocked(axios.put).mockRejectedValue({ response: { data: { message: "Adres musi wskazywać artykuł Wikipedii" } } });
  open("/places?name=Janbu");
  const details = await screen.findByRole("complementary", { name: "Szczegóły miejsca" });
  await within(details).findByRole("link", { name: "Film o ropie" });
  fireEvent.click(within(details).getByRole("button", { name: "Zapisz" }));
  expect(await within(details).findByText(/Adres musi wskazywać artykuł Wikipedii/)).toBeTruthy();
});
