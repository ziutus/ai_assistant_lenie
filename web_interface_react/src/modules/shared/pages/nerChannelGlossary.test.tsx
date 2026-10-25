import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NerChannelGlossary from "./nerChannelGlossary";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const entries = [
  { id: 1, author: "Na Wschód od Bliskiego Wschodu", canonical_name: "Pete Hegseth", aliases: ["He H"], fuzzy: true,
    note: "doc 10872", created_by: "key", created_at: "2026-10-18T08:00:00" },
];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data: { status: "success", entries, authors: [entries[0].author] } });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.patch).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.delete).mockResolvedValue({ data: { status: "success" } });
});
afterEach(cleanup);

const open = (url = "/ner-glossary") => render(
  <MemoryRouter initialEntries={[url]}><Routes><Route path="/ner-glossary" element={<NerChannelGlossary />} /></Routes></MemoryRouter>);

it("lists entries with aliases and the matching mode", async () => {
  open();
  const table = await screen.findByRole("table");
  expect(within(table).getByText("Pete Hegseth")).toBeTruthy();
  expect(within(table).getByText("He H")).toBeTruthy();
  expect(within(table).getByText(/przybliżone: tak/)).toBeTruthy();
});

it("adds an entry with one alias per line", async () => {
  open();
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Kanał"), { target: { value: "Na Wschód od Bliskiego Wschodu" } });
  fireEvent.change(screen.getByLabelText("Poprawna nazwa"), { target: { value: "Marco Rubio" } });
  fireEvent.change(screen.getByLabelText("Aliasy"), { target: { value: "Marku Rubio\n Rubia " } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/ner_channel_glossary", {
    author: "Na Wschód od Bliskiego Wschodu", canonical_name: "Marco Rubio", aliases: ["Marku Rubio", "Rubia"],
    fuzzy: true, note: null,
  }, expect.any(Object)));
  expect(await screen.findByText(/Dodano „Marco Rubio”/)).toBeTruthy();
});

it("edits aliases and the fuzzy switch", async () => {
  open();
  await screen.findByRole("table");
  fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
  fireEvent.change(screen.getByLabelText("Aliasy Pete Hegseth"), { target: { value: "He H\nHekset" } });
  fireEvent.click(screen.getByLabelText("Przybliżone Pete Hegseth"));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/ner_channel_glossary/1",
    { aliases: ["He H", "Hekset"], fuzzy: false, note: "doc 10872" }, expect.any(Object)));
});

it("deletes only after a second click", async () => {
  open();
  await screen.findByRole("table");
  fireEvent.click(screen.getByRole("button", { name: "Usuń" }));
  expect(axios.delete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Potwierdź usunięcie" }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/ner_channel_glossary/1", expect.any(Object)));
});

it("filters by channel through the URL", async () => {
  open("/ner-glossary?author=Kana%C5%82");
  await screen.findByRole("table");
  expect(vi.mocked(axios.get)).toHaveBeenCalledWith("/ner_channel_glossary",
    expect.objectContaining({ params: { author: "Kanał" } }));
});

it("shows the backend validation message", async () => {
  vi.mocked(axios.post).mockRejectedValue({ response: { data: { message: "Ten kanał ma już wpis o tej nazwie" } } });
  open();
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Kanał"), { target: { value: "K" } });
  fireEvent.change(screen.getByLabelText("Poprawna nazwa"), { target: { value: "Pete Hegseth" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
});
