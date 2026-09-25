import React from "react";
import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ContactPhotoPanel from "./ContactPhotoPanel";

vi.mock("axios");
const photo = {
  id: "photo-id", storage_key: "shared.png", photo_url: "/photo.png", user_description: "Wiedza",
  user_description_revision: 1, ai_descriptions: {}, subject_kind: "unknown", people_count: null,
  classification_revision: 0,
  contacts: [{ contact_id: 1, display_name: "Anna", depicts_contact: null, link_revision: 0 },
    { contact_id: 2, display_name: "Jan", depicts_contact: true, link_revision: 1 }],
};
beforeEach(() => {
  vi.resetAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  vi.mocked(axios.get).mockResolvedValue({ data: photo });
});
afterEach(cleanup);
const show = () => render(<ContactPhotoPanel photoId="photo-id" contactId="1" apiUrl="/api" apiKey="key"
  onClose={vi.fn()} onChange={vi.fn()} />);

it("centres the modal itself because the global CSS reset removes the dialog's default margin", () => {
  show();
  const dialog = screen.getByRole("dialog", { name: "Szczegóły zdjęcia" });
  expect(dialog.style.margin).toBe("auto");
  expect(dialog.style.padding).toBe("24px");
});

it("loads shared photo without an AI call and saves suggestions only explicitly", async () => {
  show();
  await screen.findByText(/Zmiana opisu i klasyfikacji dotyczy 2 kontaktów/);
  expect(axios.post).not.toHaveBeenCalled();
  vi.mocked(axios.post).mockResolvedValue({ data: { subject_kind: "people", people_count: 3 } });
  fireEvent.click(screen.getByRole("button", { name: "Zaproponuj klasyfikację (AI)" }));
  await waitFor(() => expect(screen.getByLabelText("Liczba osób")).toHaveProperty("value", "3"));
  expect(axios.patch).not.toHaveBeenCalled();
  vi.mocked(axios.patch).mockResolvedValue({ data: { photo: { ...photo, subject_kind: "people", people_count: 3, classification_revision: 1 } } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz klasyfikację" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/api/contact_photos/photo-id/classification",
    { subject_kind: "people", people_count: 3, classification_revision: 0 }, expect.anything()));
});

it("preserves classification and description drafts on 409 and retries with refreshed revision", async () => {
  show();
  await screen.findByLabelText("Temat zdjęcia");
  fireEvent.change(screen.getByLabelText("Temat zdjęcia"), { target: { value: "people" } });
  fireEvent.change(screen.getByLabelText("Liczba osób"), { target: { value: "4" } });
  fireEvent.change(screen.getByLabelText("Twój opis zdjęcia"), { target: { value: "Mój szkic" } });
  vi.mocked(axios.get).mockResolvedValue({ data: { ...photo, classification_revision: 8, user_description: "Inny opis" } });
  vi.mocked(axios.patch).mockRejectedValueOnce({ response: { status: 409, data: { message: "Konflikt" } } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz klasyfikację" }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("Liczba osób")).toHaveProperty("value", "4");
  expect(screen.getByLabelText("Twój opis zdjęcia")).toHaveProperty("value", "Mój szkic");
  vi.mocked(axios.patch).mockResolvedValue({ data: { photo } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz klasyfikację" }));
  await waitFor(() => expect(axios.patch).toHaveBeenLastCalledWith(expect.anything(),
    { subject_kind: "people", people_count: 4, classification_revision: 8 }, expect.anything()));
});

it("saves the nullable per-contact flag independently", async () => {
  show();
  await screen.findByLabelText("Zdjęcie przedstawia tę osobę");
  fireEvent.change(screen.getByLabelText("Zdjęcie przedstawia tę osobę"), { target: { value: "false" } });
  vi.mocked(axios.patch).mockResolvedValue({ data: { depicts_contact: false, revision: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz powiązanie" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/api/contact_photos/photo-id/contacts/1",
    { depicts_contact: false, revision: 0 }, expect.anything()));
});
