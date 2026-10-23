import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import axios from "axios";
import Persons from "./persons";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://api", apiKey: "test-key" }) };
});
vi.mock("axios");

const szewko = {
  id: 3, uuid: "u", canonical_name: "Wojciech Szewko", wikidata_qid: null, description: "Analityk Bliskiego Wschodu",
  aliases: [], links: [], kind: "public", role: "prowadzący kanał",
  sources: [{ id: 26, name: "Na Wschód od Bliskiego Wschodu", kind: "channel", role: "host" }],
};

const renderPersons = (path = "/persons") =>
  render(<MemoryRouter initialEntries={[path]}><Persons /></MemoryRouter>);

beforeEach(() => vi.resetAllMocks());
afterEach(() => cleanup());

it("marks public people with their role and shows the sources they stand behind", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { persons: [szewko], total: 1 } });
  renderPersons();

  expect(await screen.findByText("Wojciech Szewko")).toBeTruthy();
  expect(screen.getByText("publiczna · prowadzący kanał")).toBeTruthy();
  expect(screen.getByText(/Na Wschód od Bliskiego Wschodu \(prowadzący\)/)).toBeTruthy();
});

it("asks only for public people when the filter is ticked", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { persons: [szewko], total: 1 } });
  renderPersons();
  await screen.findByText("Wojciech Szewko");

  fireEvent.click(screen.getByLabelText("Tylko osoby publiczne"));

  await waitFor(() => {
    const calls = vi.mocked(axios.get).mock.calls;
    const lastCall = calls[calls.length - 1] as [string, { params: Record<string, unknown> }];
    expect(lastCall[1].params.kind).toBe("public");
  });
});

it("adds a public person and explains a name that is already in the registry", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { persons: [], total: 0 } });
  vi.mocked(axios.post).mockRejectedValue({
    response: { data: { message: "„Wojciech Szewko” już jest w rejestrze.", existing_person_id: 3 } },
  });
  renderPersons();
  await screen.findByText("Nie ma jeszcze osób publicznych.", {}, { timeout: 100 }).catch(() => null);

  fireEvent.click(screen.getByText("+ Dodaj osobę publiczną"));
  fireEvent.change(screen.getByPlaceholderText("Imię i nazwisko"), { target: { value: "Szewko" } });
  fireEvent.change(screen.getByPlaceholderText(/Kim jest/), { target: { value: "prowadzący kanał" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));

  await waitFor(() => expect(axios.post).toHaveBeenCalled());
  const [url, body] = vi.mocked(axios.post).mock.calls[0] as [string, Record<string, unknown>];
  expect(url).toBe("http://api/persons");
  expect(body).toMatchObject({ canonical_name: "Szewko", kind: "public", role: "prowadzący kanał" });
  expect(await screen.findByText(/już jest w rejestrze/)).toBeTruthy();
  expect(screen.getByText(/\/persons\/3/)).toBeTruthy();
});
