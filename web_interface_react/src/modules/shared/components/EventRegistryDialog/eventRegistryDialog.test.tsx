import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import EventRegistryDialog from "./eventRegistryDialog";

vi.mock("axios");
const mocked = vi.mocked(axios, true);

const headers = { "x-api-key": "k" };
const kinds = [{ code: "other", label: "Inne" }, { code: "election", label: "Wybory" }];
const candidate = { reason: "alias", score: 1, event: { id: 68, title: "Krajowa Konwencja Demokratów 2024 (Chicago)", event_date: "2024-08-19" } };

const mockGets = (candidates: unknown[]) => {
  mocked.get.mockImplementation(async (url: string) => {
    if (url.endsWith("/geo_event_kinds")) return { data: { kinds } };
    if (url.endsWith("/world_events/candidates")) return { data: { candidates } };
    throw new Error(`unexpected GET ${url}`);
  });
};

const renderDialog = (onDone = vi.fn(), onClose = vi.fn()) => {
  render(<EventRegistryDialog name="Konwencja Demokratów" docId={11237} apiUrl="http://api" headers={headers}
    onClose={onClose} onDone={onDone} />);
  return { onDone, onClose };
};

beforeEach(() => { mocked.post.mockResolvedValue({ data: {} }); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("looks up registry candidates for the marked name when it opens", async () => {
  mockGets([candidate]);
  renderDialog();

  expect(await screen.findByText(/#68 Krajowa Konwencja Demokratów 2024 \(Chicago\)/)).toBeTruthy();
  expect(mocked.get).toHaveBeenCalledWith("http://api/world_events/candidates",
    expect.objectContaining({ params: { name: "Konwencja Demokratów" } }));
});

it("links the name to an existing event for THIS document only, creating nothing", async () => {
  mockGets([candidate]);
  const { onDone } = renderDialog();

  fireEvent.click(await screen.findByLabelText(/Tak, powiąż z: #68/));
  fireEvent.click(screen.getByRole("button", { name: "Powiąż z wydarzeniem" }));

  await waitFor(() => expect(onDone).toHaveBeenCalled());
  expect(mocked.post).toHaveBeenCalledTimes(1);
  expect(mocked.post).toHaveBeenCalledWith("http://api/world_events/mentions/link",
    { name: "Konwencja Demokratów", event_id: 68, document_ids: [11237] }, { headers });
  expect(onDone.mock.calls[0][0]).toContain("#68");
});

it("creates a confirmed event with the marked name as alias, then links it", async () => {
  mockGets([]);
  mocked.post.mockImplementation(async (url: string) => (
    url.endsWith("/geo_events") ? { data: { event: { id: 70, title: "Krajowa Konwencja Demokratów 2024 (Chicago)" } } } : { data: {} }
  ));
  const { onDone } = renderDialog();

  const title = await screen.findByLabelText(/Tytuł wydarzenia/);
  fireEvent.change(title, { target: { value: "Krajowa Konwencja Demokratów 2024 (Chicago)" } });
  fireEvent.change(screen.getByLabelText(/Rodzaj/), { target: { value: "election" } });
  fireEvent.change(screen.getByPlaceholderText("RRRR-MM-DD"), { target: { value: "2024-08-19" } });
  fireEvent.click(screen.getByRole("button", { name: "Utwórz wydarzenie i powiąż" }));

  await waitFor(() => expect(onDone).toHaveBeenCalled());
  expect(mocked.post).toHaveBeenNthCalledWith(1, "http://api/geo_events", {
    title: "Krajowa Konwencja Demokratów 2024 (Chicago)", kind: "election", aliases: ["Konwencja Demokratów"],
    status: "confirmed", event_date: "2024-08-19",
  }, { headers });
  expect(mocked.post).toHaveBeenNthCalledWith(2, "http://api/world_events/mentions/link",
    { name: "Konwencja Demokratów", event_id: 70, document_ids: [11237] }, { headers });
});

it("refuses a malformed date before sending anything", async () => {
  mockGets([]);
  renderDialog();

  fireEvent.change(await screen.findByPlaceholderText("RRRR-MM-DD"), { target: { value: "sierpień 2024" } });

  expect(screen.getByRole("alert").textContent).toContain("RRRR-MM-DD");
  expect((screen.getByRole("button", { name: "Utwórz wydarzenie i powiąż" }) as HTMLButtonElement).disabled).toBe(true);
  expect(mocked.post).not.toHaveBeenCalled();
});

it("shows a plain error and keeps the dialog open when saving fails", async () => {
  mockGets([]);
  mocked.post.mockRejectedValue(new Error("boom"));
  const { onDone, onClose } = renderDialog();

  fireEvent.click(await screen.findByRole("button", { name: "Utwórz wydarzenie i powiąż" }));

  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(onDone).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
});

it("replaces the current link: unlinks the old event first, then links the chosen one", async () => {
  mockGets([{ reason: "alias", score: 1, event: { id: 71, title: "Krajowa Konwencja Demokratów 2020", event_date: "2020-08-17" } }]);
  render(<EventRegistryDialog name="Konwencja Demokratów" docId={11237} apiUrl="http://api" headers={headers}
    current={{ id: 68, surface: "Konwencja Demokratów" }} onClose={vi.fn()} onDone={vi.fn()} />);

  expect(screen.getByText(/Teraz powiązane z wydarzeniem #68/)).toBeTruthy();
  fireEvent.click(await screen.findByLabelText(/Tak, powiąż z: #71/));
  fireEvent.click(screen.getByRole("button", { name: "Powiąż z wydarzeniem" }));

  await waitFor(() => expect(mocked.post).toHaveBeenCalledTimes(2));
  expect(mocked.post).toHaveBeenNthCalledWith(1, "http://api/world_events/mentions/unlink",
    { name: "Konwencja Demokratów", event_id: 68, document_id: 11237 }, { headers });
  expect(mocked.post).toHaveBeenNthCalledWith(2, "http://api/world_events/mentions/link",
    { name: "Konwencja Demokratów", event_id: 71, document_ids: [11237] }, { headers });
});
