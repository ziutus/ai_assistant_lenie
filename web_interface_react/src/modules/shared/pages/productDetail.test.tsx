import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ProductDetail from "./productDetail";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

beforeEach(() => vi.resetAllMocks());
afterEach(() => cleanup());

const product = {
  name: "Starlink", description: null, variants: ["Starlinka", "Starlinek"], mentions: 7,
  documents: [{ id: 10872, title: "Film o satelitach", mentions: 7, entity_id: 5, document_type: "youtube", created_at: "2026-10-01T10:00:00" }],
};

const renderPage = () => render(
  <MemoryRouter initialEntries={["/products/Starlink"]}>
    <Routes><Route path="/products/:name" element={<ProductDetail />} /></Routes>
  </MemoryRouter>);

it("shows the spellings and the documents mentioning the product", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: product });
  renderPage();
  expect(await screen.findByRole("heading", { name: /Starlink/ })).toBeTruthy();
  expect(screen.getByText("Starlinka, Starlinek")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Film o satelitach" }).getAttribute("href")).toBe("/webpage/10872");
  expect(screen.getByRole("link", { name: "NER" }).getAttribute("href")).toBe("/ner/10872");
  expect(axios.get).toHaveBeenCalledWith("/entity_product", { headers: { "x-api-key": "test-key" }, params: { name: "Starlink" } });
});

it("saves the description for the whole product", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: product });
  vi.mocked(axios.put).mockResolvedValue({ data: { description: "Satelitarny internet SpaceX." } });
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Dodaj opis" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Opis produktu" }), { target: { value: "Satelitarny internet SpaceX." } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith("/entity_product/description",
    { name: "Starlink", description: "Satelitarny internet SpaceX." }, { headers: { "x-api-key": "test-key" } }));
  expect(await screen.findByText("Satelitarny internet SpaceX.")).toBeTruthy();
});

it("reports a missing product", async () => {
  vi.mocked(axios.get).mockRejectedValue({ response: { data: { message: "Nie znaleziono produktu." } } });
  renderPage();
  expect((await screen.findByRole("alert")).textContent).toContain("Nie znaleziono produktu.");
});
