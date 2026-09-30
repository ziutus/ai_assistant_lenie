import React from "react";
import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TopicDetail } from "./topics";

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("axios", () => ({ default: { create: () => api, isAxiosError: () => false } }));

const initialTopic = {
  id: 1, name: "Podróże", description: "Plany podróży", archived_at: null as string | null,
  items: { document: [], contact: [], chat_conversation: [], chat_message: [], contact_group_event: [
    { id: 9, entity_id: 7, note: null,
      entity: { id: 7, title: "Wyjazd", event_date: "2026-09-01", event_date_end: "2026-09-03" } },
  ] },
};
let topic = structuredClone(initialTopic);

async function openTopic() {
  render(<MemoryRouter initialEntries={["/topics/1"]}>
    <Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes>
  </MemoryRouter>);
  await screen.findByRole("heading", { name: "Podróże" });
}

beforeEach(() => {
  vi.clearAllMocks();
  topic = structuredClone(initialTopic);
  api.get.mockImplementation(async () => ({ data: { topic } }));
  api.patch.mockImplementation(async (_url, changes) => {
    topic = { ...topic, ...changes };
    if ("archived" in changes) topic.archived_at = changes.archived ? "2026-09-29" : null;
    return { data: { topic } };
  });
  api.post.mockResolvedValue({ data: {} });
});
afterEach(cleanup);

describe("TopicDetail", () => {
  it("presents links without forms and restores saved values on cancel", async () => {
    await openTopic();
    expect(screen.getByText("Plany podróży")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByLabelText("Typ")).toBeNull();
    expect(screen.getByRole("link", { name: "Wyjazd — 2026-09-01 – 2026-09-03" }).getAttribute("href"))
      .toBe("/contact-events/7");
    fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: "Zmiana" } });
    fireEvent.change(screen.getByLabelText("Opis"), { target: { value: "Nowy opis" } });
    fireEvent.click(screen.getByRole("button", { name: "Anuluj" }));
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
    expect((screen.getByLabelText("Nazwa") as HTMLInputElement).value).toBe("Podróże");
    expect((screen.getByLabelText("Opis") as HTMLTextAreaElement).value).toBe("Plany podróży");
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("saves changes and returns to presentation", async () => {
    await openTopic();
    fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: "Wyprawy" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    await screen.findByRole("heading", { name: "Wyprawy" });
    expect(api.patch).toHaveBeenCalledWith("/topics/1", { name: "Wyprawy", description: "Plany podróży" });
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("archives and restores from presentation", async () => {
    await openTopic();
    fireEvent.click(screen.getByRole("button", { name: "Archiwizuj temat" }));
    fireEvent.click(await screen.findByRole("button", { name: "Przywróć temat" }));
    await screen.findByRole("button", { name: "Archiwizuj temat" });
    expect(api.patch).toHaveBeenNthCalledWith(1, "/topics/1", { archived: true });
    expect(api.patch).toHaveBeenNthCalledWith(2, "/topics/1", { archived: false });
  });

  it("expands event linking and collapses it after success", async () => {
    await openTopic();
    fireEvent.click(screen.getByRole("button", { name: "+ Dodaj powiązanie" }));
    fireEvent.change(screen.getByLabelText("Typ"), { target: { value: "contact_group_event" } });
    fireEvent.change(screen.getByLabelText("ID"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/topics/1/items",
      { entity_type: "contact_group_event", entity_id: 7, note: null }));
    await screen.findByRole("heading", { name: "Podróże" });
    expect(screen.queryByLabelText("Typ")).toBeNull();
  });

  it("keeps the edit form and draft on failure", async () => {
    await openTopic();
    api.patch.mockRejectedValueOnce(new Error("Failed"));
    fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
    fireEvent.change(screen.getByLabelText("Nazwa"), { target: { value: "Szkic" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((screen.getByLabelText("Nazwa") as HTMLInputElement).value).toBe("Szkic");
  });
});
