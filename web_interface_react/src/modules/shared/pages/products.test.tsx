import axios from "axios";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Products from "./products";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

beforeEach(() => vi.resetAllMocks());
afterEach(() => cleanup());

it("lists products with a link to each product page", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 2, products: [
    { name: "Starlink", description: "Satelitarny internet.", mentions: 5, document_count: 2, documents: [] },
    { name: "Star Shield", description: null, mentions: 1, document_count: 1, documents: [] },
  ] } });
  render(<MemoryRouter initialEntries={["/products?q=star"]}><Products /></MemoryRouter>);
  const list = await screen.findByRole("list", { name: "Produkty" });
  const [first, second] = within(list).getAllByRole("listitem");
  expect(first.textContent).toContain("Satelitarny internet.");
  expect(within(first).getByRole("link", { name: /Starlink/ }).getAttribute("href")).toBe("/products/Starlink");
  expect(within(second).getByRole("link", { name: /Star Shield/ }).getAttribute("href")).toBe("/products/Star%20Shield");
  expect(second.textContent).toContain("Brak opisu");
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith("/entity_products", {
    headers: { "x-api-key": "test-key" }, params: { q: "star", limit: 50, offset: 0 } }));
});

it("explains an empty result", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { total: 0, products: [] } });
  render(<MemoryRouter><Products /></MemoryRouter>);
  expect(await screen.findByText("Brak produktów.")).toBeTruthy();
});
