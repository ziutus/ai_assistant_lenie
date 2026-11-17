import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PersonTerritories from "./personTerritories";

vi.mock("axios");

const tie = (overrides: Record<string, unknown> = {}) => ({
  id: 1, kind: "country", slug: "jemen", name_pl: "Jemen", tag: "kraj-jemen", relation: "holds_office_in",
  relation_label: "pełni funkcję w", note: "rzecznik", valid_from: "2026-01-01", valid_to: null, ...overrides,
});
const payload = (overrides: Record<string, unknown> = {}) => ({
  data: {
    status: "success",
    territories: [tie(), tie({ id: 2, kind: "region", slug: "bliski-wschod", name_pl: "Bliski Wschód",
      tag: "miejsce-bliski-wschod", relation: "active_in", relation_label: "działa w", note: null, valid_from: null })],
    suggestions: [{ kind: "country", slug: "iran", name_pl: "Iran", documents: 3 }],
    relations: { citizen_of: "obywatelstwo", holds_office_in: "pełni funkcję w", active_in: "działa w", linked_to: "powiązanie" },
    regions: [{ slug: "bliski-wschod", name_pl: "Bliski Wschód" }, { slug: "sahel", name_pl: "Sahel" }],
    ...overrides,
  },
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue(payload());
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.delete).mockResolvedValue({ data: { status: "success" } });
});
afterEach(cleanup);

const show = () => render(<PersonTerritories personId={7} apiUrl="" apiKey="k" />);

it("lists countries and regions with the kind of tie, the period and the note", async () => {
  show();
  const section = await screen.findByRole("region", { name: "Kraje i regiony osoby" });
  const items = (await within(section).findAllByRole("listitem")).map((item) => item.textContent);
  expect(within(section).getByText("Kraje i regiony (2)")).toBeTruthy();
  expect(items[0]).toContain("pełni funkcję w");
  expect(items[0]).toContain("(od 2026-01-01)");
  expect(items[0]).toContain("— rzecznik");
  expect(items[1]).toContain("Bliski Wschód");
  expect(vi.mocked(axios.get).mock.calls[0][0]).toBe("/persons/7/territories");
});

it("adds a country tie with relation, dates and note", async () => {
  show();
  await screen.findByText("Jemen");
  fireEvent.change(screen.getByLabelText("Obszar"), { target: { value: "jemen" } });
  fireEvent.change(screen.getByLabelText("Rodzaj powiązania"), { target: { value: "citizen_of" } });
  fireEvent.change(screen.getByLabelText("Od"), { target: { value: "1978-07-17" } });
  fireEvent.change(screen.getByLabelText("Do"), { target: { value: "2012-02-27" } });
  fireEvent.change(screen.getByLabelText("Notatka do powiązania"), { target: { value: " prezydent " } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj powiązanie" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/persons/7/territories", {
    kind: "country", slug: "jemen", relation: "citizen_of", note: "prezydent",
    valid_from: "1978-07-17", valid_to: "2012-02-27",
  }, expect.any(Object)));
});

it("offers macro-regions after switching the kind and keeps the add button disabled until one is chosen", async () => {
  show();
  await screen.findByText("Jemen");
  const add = screen.getByRole("button", { name: "Dodaj powiązanie" }) as HTMLButtonElement;
  expect(add.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Rodzaj obszaru"), { target: { value: "region" } });
  const names = within(screen.getByLabelText("Obszar")).getAllByRole("option").map((option) => option.textContent);
  expect(names).toEqual(["— wybierz region —", "Bliski Wschód", "Sahel"]);
  fireEvent.change(screen.getByLabelText("Obszar"), { target: { value: "sahel" } });
  expect(add.disabled).toBe(false);
  fireEvent.click(add);
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/persons/7/territories",
    expect.objectContaining({ kind: "region", slug: "sahel" }), expect.any(Object)));
});

it("adds a suggestion from the person's documents with the chosen relation", async () => {
  show();
  await screen.findByText("Jemen");
  fireEvent.change(screen.getByLabelText("Rodzaj powiązania"), { target: { value: "linked_to" } });
  fireEvent.click(screen.getByRole("button", { name: /\+ Iran ×3/ }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/persons/7/territories",
    { kind: "country", slug: "iran", relation: "linked_to" }, expect.any(Object)));
});

it("removes a tie and reloads the list", async () => {
  show();
  await screen.findByText("Jemen");
  fireEvent.click(screen.getByRole("button", { name: "Usuń Jemen: pełni funkcję w" }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/persons/7/territories/1", expect.any(Object)));
  await waitFor(() => expect(vi.mocked(axios.get).mock.calls.length).toBe(2));
});

it("shows a backend validation message and a failed load without breaking the page", async () => {
  vi.mocked(axios.post).mockRejectedValue({ response: { data: { message: "valid_to must not be earlier than valid_from" } } });
  show();
  await screen.findByText("Jemen");
  fireEvent.change(screen.getByLabelText("Obszar"), { target: { value: "jemen" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj powiązanie" }));
  expect((await screen.findByRole("alert")).textContent).toContain("valid_to must not be earlier");
  cleanup();
  vi.mocked(axios.get).mockRejectedValue(new Error("Network Error"));
  show();
  expect((await screen.findByRole("alert")).textContent).toContain("Network Error");
});

it("says there are no ties yet", async () => {
  vi.mocked(axios.get).mockResolvedValue(payload({ territories: [], suggestions: [] }));
  show();
  expect(await screen.findByText("Brak powiązań.")).toBeTruthy();
});
