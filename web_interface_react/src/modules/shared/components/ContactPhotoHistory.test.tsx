import React from "react";
import axios from "axios";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ContactPhotoHistory from "./ContactPhotoHistory";

vi.mock("axios");
const photo = { storage_key: "contacts/one/photo.png", user_description: null, user_description_revision: 0, ai_descriptions: {} };
const older = { ...photo, created_at: "2026-09-01T12:00:00", is_current: false, photo_url: "/old.png", thumbnail_url: "/thumb.jpg" };
const current = { ...older, storage_key: "contacts/one/photos/new.png", is_current: true, thumbnail_url: null, photo_url: "/new.png" };

function show(onRestored = vi.fn()) {
  render(<ContactPhotoHistory contactId="494" apiUrl="/api" apiKey="test" onRestored={onRestored} />);
  return screen.getByText("Historia zdjęć").closest("details")!;
}
function expand(details: HTMLDetailsElement) {
  details.open = true;
  fireEvent(details, new Event("toggle"));
}

describe("contact photo history", () => {
  beforeEach(() => vi.resetAllMocks());
  afterEach(cleanup);

  it("opens details of an inherited historical photo by photo UUID", async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { history: [{ ...older, id: "shared-photo" }] } });
    const open = vi.fn();
    render(<ContactPhotoHistory contactId="child" apiUrl="/api" apiKey="test" onRestored={vi.fn()} onOpenPhoto={open} />);
    expand(screen.getByText("Historia zdjęć").closest("details")!);
    fireEvent.click(await screen.findByRole("button", { name: "Szczegóły zdjęcia" }));
    expect(open).toHaveBeenCalledWith("shared-photo");
    expect(axios.post).not.toHaveBeenCalled();
  });

  it("loads lazily, restores a photo and refreshes current flags", async () => {
    vi.mocked(axios.get).mockResolvedValueOnce({ data: { history: [current, older] } })
      .mockResolvedValueOnce({ data: { history: [{ ...older, is_current: true }] } });
    let resolveRestore!: (value: unknown) => void;
    vi.mocked(axios.post).mockImplementation(() => new Promise((resolve) => { resolveRestore = resolve; }));
    const onRestored = vi.fn();
    const details = show(onRestored);
    expect(details.open).toBe(false);
    expect(axios.get).not.toHaveBeenCalled();
    expand(details);
    const restore = await screen.findByRole("button", { name: "Przywróć to zdjęcie" });
    expect(axios.get).toHaveBeenCalledWith("/api/contacts/494/photo/history", { headers: { "x-api-key": "test" } });
    expect(screen.getByRole("button", { name: "Aktualne zdjęcie" })).toHaveProperty("disabled", true);
    expect(screen.getAllByRole("img").map((img) => img.getAttribute("src"))).toEqual(["/new.png", "/thumb.jpg"]);
    fireEvent.click(restore);
    expect(screen.getByRole("button", { name: "Przywracanie…" })).toHaveProperty("disabled", true);
    expect(axios.post).toHaveBeenCalledWith("/api/contacts/494/photo/restore", { storage_key: photo.storage_key },
      { headers: { "x-api-key": "test" } });
    await act(async () => { resolveRestore({ data: { photo_url: "/restored.png", photo } }); });
    expect(onRestored).toHaveBeenCalledWith("/restored.png", photo);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("button", { name: "Przywróć to zdjęcie" })).toBeNull();
    expect(screen.getByRole("button", { name: "Aktualne zdjęcie" })).toHaveProperty("disabled", true);
  });

  it("shows the restore error on the card and allows retry", async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { history: [older] } });
    vi.mocked(axios.post).mockRejectedValue({ response: { data: { message: "Nie można przywrócić zdjęcia" } } });
    const onRestored = vi.fn();
    expand(show(onRestored));
    fireEvent.click(await screen.findByRole("button", { name: "Przywróć to zdjęcie" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Nie można przywrócić zdjęcia");
    expect(screen.getByRole("button", { name: "Przywróć to zdjęcie" })).toHaveProperty("disabled", false);
    expect(onRestored).not.toHaveBeenCalled();
  });

  it("does not notify the parent after unmount during restore", async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { history: [older] } });
    let resolveRestore!: (value: unknown) => void;
    vi.mocked(axios.post).mockImplementation(() => new Promise((resolve) => { resolveRestore = resolve; }));
    const onRestored = vi.fn();
    expand(show(onRestored));
    fireEvent.click(await screen.findByRole("button", { name: "Przywróć to zdjęcie" }));
    cleanup();
    await act(async () => { resolveRestore({ data: { photo_url: "/restored.png", photo } }); });
    expect(onRestored).not.toHaveBeenCalled();
    expect(axios.get).toHaveBeenCalledTimes(1);
  });
});
