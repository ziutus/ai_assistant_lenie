import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Recipes from "./recipes";
import Recipe from "./recipe";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const list = {
  total: 2,
  recipes: [
    { id: 11, title: "Gulasz z soczewicą", tags: ["przepis", "obiad", "wege"], servings: "2", meals: ["obiad"], wege: true, ingredient_count: 7, note: null, thumb_url: "http://minio/t11.jpg" },
    { id: 12, title: "Guacamole", tags: ["przepis"], servings: null, meals: [], wege: false, ingredient_count: 4, note: "Książka, s. 62" },
  ],
  meals: [
    { tag: "obiad", label: "Obiad", count: 40 },
    { tag: "kolacja", label: "Kolacja", count: 30 },
  ],
  wege_count: 25,
};
const detail = {
  id: 11, title: "Gulasz z soczewicą", tags: ["przepis"], byline: "Autorka", note: "s. 91", servings: "2", meals: ["obiad"],
  section: null, nutrition: null, notes: ["Gotowy w 20 minut."],
  ingredients: [{ text: "spód", label: true }, { text: "300 g soczewicy", label: false }],
  method: ["Podduś cebulę.", "Dodaj soczewicę."], menu_slots: ["miesiąc I, tydzień 1, obiad"],
  photos: [{ url: "http://minio/11.jpg", thumb_url: "http://minio/t11.jpg", caption: "gulasz" }],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url: string) => (
    url.endsWith("/recipes/11") ? { data: { recipe: detail } } : { data: list }));
});
afterEach(cleanup);

it("lists recipes with meal counts and sends the filters from the URL", async () => {
  render(<MemoryRouter initialEntries={["/recipes?q=soczewica&meal=obiad&wege=1"]}><Routes><Route path="/recipes" element={<Recipes />} /></Routes></MemoryRouter>);
  expect(await screen.findByRole("link", { name: "Gulasz z soczewicą" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Obiad (40)" })).toBeTruthy();
  expect(document.querySelector('img[src="http://minio/t11.jpg"]')).toBeTruthy();
  expect(screen.getByRole("button", { name: "Z wersją wege (25)" })).toBeTruthy();
  expect(vi.mocked(axios.get)).toHaveBeenCalledWith("/recipes", expect.objectContaining({
    params: { limit: "50", offset: "0", meal: "obiad", wege: "1", q: "soczewica" } }));
});

it("searches when the user submits a query", async () => {
  render(<MemoryRouter initialEntries={["/recipes"]}><Routes><Route path="/recipes" element={<Recipes />} /></Routes></MemoryRouter>);
  await screen.findByRole("link", { name: "Guacamole" });
  fireEvent.change(screen.getByPlaceholderText(/soczewica/), { target: { value: "pęczak" } });
  fireEvent.click(screen.getByRole("button", { name: "Szukaj" }));
  await waitFor(() => expect(vi.mocked(axios.get)).toHaveBeenCalledWith("/recipes", expect.objectContaining({
    params: expect.objectContaining({ q: "pęczak" }) })));
});

it("shows one recipe split into ingredients, method and meal-plan slots", async () => {
  render(<MemoryRouter initialEntries={["/recipes/11"]}><Routes><Route path="/recipes/:id" element={<Recipe />} /></Routes></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Gulasz z soczewicą" })).toBeTruthy();
  expect(screen.getByText("300 g soczewicy")).toBeTruthy();
  expect(screen.getByText("Dodaj soczewicę.")).toBeTruthy();
  expect(screen.getByText("miesiąc I, tydzień 1, obiad")).toBeTruthy();
  expect(screen.getByText("Gotowy w 20 minut.")).toBeTruthy();
  expect((screen.getByAltText("gulasz") as HTMLImageElement).src).toBe("http://minio/11.jpg");
});
