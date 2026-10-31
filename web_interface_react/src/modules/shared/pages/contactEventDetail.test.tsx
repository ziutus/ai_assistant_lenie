import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ContactEventDetail from "./contactEventDetail";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("axios", () => ({ default: api }));

const event = {
  id: 12, group_id: null, group_name: null, title: "AI Jam Łódź #32", event_date: "2026-10-29",
  event_date_end: null, summary: null, source_document_id: null, source_document_title: null,
  participants: [{ id: 5, first_name: "Jarek", last_name: null, display_name: "Jarek" }],
  links: [{ id: 1, link_type: "luma", url: "https://luma.com/096jxav1", label: null }],
  created_at: "", updated_at: "",
};

async function openEvent() {
  render(<MemoryRouter initialEntries={["/contact-events/12"]}>
    <Routes><Route path="/contact-events/:id" element={<ContactEventDetail />} /></Routes>
  </MemoryRouter>);
  await screen.findByRole("heading", { name: "AI Jam Łódź #32" });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (url: string) => url.includes("/contact_groups")
    ? { data: { contact_groups: [] } } : { data: { event } });
});
afterEach(cleanup);

describe("ContactEventDetail links", () => {
  it("shows the event links with their type", async () => {
    await openEvent();
    expect(screen.getByRole("link", { name: "https://luma.com/096jxav1" }).getAttribute("href"))
      .toBe("https://luma.com/096jxav1");
    expect(screen.getByText(/Luma:/)).toBeTruthy();
  });

  it("adds a link and removes one", async () => {
    api.post.mockResolvedValue({ data: { link: { id: 2, link_type: "slides", url: "https://x.pl/s", label: "Slajdy" } } });
    api.delete.mockResolvedValue({ data: {} });
    await openEvent();
    fireEvent.change(screen.getByLabelText("Typ linku"), { target: { value: "slides" } });
    fireEvent.change(screen.getByLabelText("Adres linku"), { target: { value: "https://x.pl/s" } });
    fireEvent.change(screen.getByLabelText("Opis linku"), { target: { value: "Slajdy" } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj link" }));
    expect(await screen.findByRole("link", { name: "Slajdy" })).toBeTruthy();
    expect(api.post.mock.calls[0][0]).toMatch(/\/contact_group_events\/12\/links$/);
    expect(api.post.mock.calls[0][1]).toEqual({ link_type: "slides", url: "https://x.pl/s", label: "Slajdy" });
    fireEvent.click(screen.getByRole("button", { name: "Usuń link https://luma.com/096jxav1" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "https://luma.com/096jxav1" })).toBeNull());
    expect(api.delete.mock.calls[0][0]).toMatch(/\/contact_event_links\/1$/);
  });
});
