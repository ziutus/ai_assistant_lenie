import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ContactInterestsEducation from "./ContactInterestsEducation";

vi.mock("axios");
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async url => {
    if (String(url).endsWith("/education")) return { data: { education: [{
      id: 3, institution: "University", degree: "master", field_of_study: "Physics",
      start_date: "2010-09-01", end_date: null, notes: null,
    }] } };
    if (String(url).endsWith("/contact_interests")) return { data: { contact_interests: [
      { id: 2, name: "Music" }, { id: 4, name: "Hiking" },
    ] } };
    return { data: { contact: { interests: [{ id: 2, name: "Music" }] } } };
  });
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
  vi.mocked(axios.delete).mockResolvedValue({ data: {} });
});
const setup = (editable = true) => render(<MemoryRouter>
  <ContactInterestsEducation contactId="1" editable={editable} onChanged={vi.fn()} />
</MemoryRouter>);

it("shows linked interest chips and education without edit controls in view mode", async () => {
  setup(false);
  expect((await screen.findByRole("link", { name: "Music" })).getAttribute("href")).toBe("/contacts?interest_ids=2");
  expect(screen.getByText("University")).toBeTruthy();
  expect(screen.getByText("Physics · Magister")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Edytuj" })).toBeNull();
});

it("assigns an existing interest and removes an assigned interest", async () => {
  setup();
  await screen.findByText("University");
  await waitFor(() => expect(screen.getByRole("button", { name: "Usuń zainteresowanie Music" }).closest("button")?.disabled).toBe(false));
  fireEvent.change(screen.getByLabelText("Zainteresowanie"), { target: { value: "4" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/contacts/1/interests", { interest_id: 4 }, expect.anything()));
  await waitFor(() => expect(screen.getByRole("button", { name: "Usuń zainteresowanie Music" }).closest("button")?.disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Usuń zainteresowanie Music" }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/contacts/1/interests/2", expect.anything()));
});

it("edits education using the contact-scoped endpoint and retains form on failure", async () => {
  setup();
  await screen.findByText("University");
  await waitFor(() => expect(screen.getByRole("button", { name: "Edytuj" }).closest("button")?.disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
  fireEvent.change(screen.getByLabelText("Kierunek"), { target: { value: "Mathematics" } });
  vi.mocked(axios.patch).mockRejectedValueOnce({ response: { data: { message: "Invalid dates" } } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz wykształcenie" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Invalid dates");
  expect(screen.getByLabelText("Kierunek")).toHaveProperty("value", "Mathematics");
  expect(axios.patch).toHaveBeenCalledWith("/contacts/1/education/3", expect.objectContaining({
    institution: "University", field_of_study: "Mathematics", degree: "master",
  }), expect.anything());
});

it("adds education and deletes an entry after confirmation", async () => {
  setup();
  await screen.findByText("University");
  await waitFor(() => expect(screen.getByRole("button", { name: "Dodaj wykształcenie" }).closest("button")?.disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Dodaj wykształcenie" }));
  fireEvent.change(screen.getByLabelText("Uczelnia / szkoła *"), { target: { value: "School" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz wykształcenie" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/contacts/1/education", expect.objectContaining({ institution: "School" }), expect.anything()));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Zapisz wykształcenie" })).toBeNull());
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Usuń" }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/contacts/1/education/3", expect.anything()));
  confirm.mockRestore();
});
