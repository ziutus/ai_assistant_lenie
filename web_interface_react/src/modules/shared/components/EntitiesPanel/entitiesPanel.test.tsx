import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import EntitiesPanel, { EntityChips } from "./entitiesPanel";

vi.mock("axios");
afterEach(cleanup);
const place = { id: 7, text: "Jemenu Północnego", count: 2 };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [place], placeName: [{ id: 8, text: "Aden", count: 1 }] } } }));
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
});
const openMenu = async () => fireEvent.click(await screen.findByRole("button", { name: place.text }));

it("renames a place without edit mode and refetches entities", async () => {
  render(<EntitiesPanel docId={10753} />);
  await openMenu();
  expect(screen.getAllByRole("menuitem")).toHaveLength(4);
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  const input = screen.getByRole("textbox", { name: "Popraw nazwę miejsca" });
  expect((input as HTMLInputElement).value).toBe(place.text);
  fireEvent.change(input, { target: { value: " Jemen Północny " } });
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/website_entities/7",
    { text: "Jemen Północny" }, { headers: expect.objectContaining({ "Content-Type": "application/json" }) }));
  expect(await screen.findByText("Nazwa miejsca została poprawiona.")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledTimes(3);
});

it("shows a backend conflict and keeps the form open", async () => {
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { message: "Wybierz „Połącz z innym miejscem”." } } });
  render(<EntitiesPanel docId={10753} />);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  expect(await screen.findByText("Wybierz „Połącz z innym miejscem”.")).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeTruthy();
});

it.each(["× Usuń encję", "🚫 Usuń i nie wykrywaj więcej", "Połącz z innym miejscem"])(
  "opens the existing %s flow without edit mode", async (action) => {
    render(<EntitiesPanel docId={10753} />);
    await openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: action }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: "Edytuj" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "✕ anuluj" })).toBeTruthy();
    if (action !== "Połącz z innym miejscem") expect(screen.getByRole("combobox")).toBeTruthy();
  },
);

it("closes on outside pointerdown and Escape, and clears rename on document change", async () => {
  const view = render(<EntitiesPanel docId={10753} />);
  await openMenu();
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("menu")).toBeNull();
  await openMenu();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  view.rerender(<EntitiesPanel docId={10754} />);
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
});

it("preserves reader highlight behavior when menuActions is absent", () => {
  const highlight = vi.fn();
  render(<EntityChips label="Miejsca" items={[place]} highlightMode onHighlight={highlight} />);
  fireEvent.click(screen.getByRole("button"));
  expect(highlight).toHaveBeenCalledWith(place);
  expect(screen.queryByRole("menu")).toBeNull();
});

it("submits rename with Enter without submitting the document form", async () => {
  const submitDocument = vi.fn((event) => event.preventDefault());
  render(<form onSubmit={submitDocument}><EntitiesPanel docId={10753} /></form>);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" }), { key: "Enter" });
  await waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(1));
  expect(submitDocument).not.toHaveBeenCalled();
});

it("omits merge when there is no other place and keeps edit delete working", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: {
    job: null, entities: { persName: [], orgName: [], geogName: [place], placeName: [] },
  } });
  render(<EntitiesPanel docId={10753} />);
  await openMenu();
  expect(screen.queryByRole("menuitem", { name: "Połącz z innym miejscem" })).toBeNull();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
  fireEvent.click(screen.getByTitle("Usuń encję (dla osoby usuwa też powiązanie z rejestrem)"));
  expect(screen.getByRole("combobox")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Zakończ edycję" }));
  expect(screen.queryByRole("combobox")).toBeNull();
});
