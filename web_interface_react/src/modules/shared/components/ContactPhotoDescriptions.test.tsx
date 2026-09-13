import React from "react";
import axios from "axios";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ContactPhotoDescriptions, { type ContactPhotoData } from "./ContactPhotoDescriptions";

vi.mock("axios");
const gemma = "google/gemma-4-31B-it";
const mistral = "mistralai/Mistral-Small-4-119B-2603";
const initial: ContactPhotoData = { storage_key: "photo.png", user_description: "To bliźnięta", user_description_revision: 1, ai_descriptions: {} };
const result = (model: string, text: string) => ({ data: { photo: {
  ...initial, ai_descriptions: { [model]: { model, text, generated_at: "2026-09-13T12:00:00Z", prompt_tokens: 100, completion_tokens: 20, latency_ms: 500 } },
} } });

function Harness() {
  const [photo, setPhoto] = React.useState(initial);
  return <ContactPhotoDescriptions photo={photo} onChange={setPhoto} apiUrl="/api" apiKey="test" contactId="493" />;
}

describe("contact photo descriptions", () => {
  beforeEach(() => vi.resetAllMocks());
  afterEach(cleanup);

  it("keeps both out-of-order model results and an unsaved user draft", async () => {
    const resolve: Record<string, (value: unknown) => void> = {};
    vi.mocked(axios.post).mockImplementation((_url, body: any) => new Promise((done) => { resolve[body.model] = done; }));
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Wygeneruj i porównaj dwa opisy" }));
    fireEvent.change(screen.getByLabelText("Twój opis zdjęcia"), { target: { value: "Wiem, że to mąż i bliźnięta" } });
    await act(async () => { resolve[mistral](result(mistral, "Opis Mistrala")); });
    await act(async () => { resolve[gemma](result(gemma, "Opis Gemmy")); });
    expect(screen.getByText("Opis Mistrala")).toBeTruthy();
    expect(screen.getByText("Opis Gemmy")).toBeTruthy();
    expect(screen.getByLabelText("Twój opis zdjęcia")).toHaveProperty("value", "Wiem, że to mąż i bliźnięta");
    expect(axios.patch).not.toHaveBeenCalled();
    expect(vi.mocked(axios.post).mock.calls.every((call) => !("user_description" in (call[1] as object)))).toBe(true);
  });

  it("keeps the successful result when the other model fails", async () => {
    vi.mocked(axios.post).mockImplementation((_url, body: any) => body.model === gemma
      ? Promise.resolve(result(gemma, "Zapisany opis Gemmy"))
      : Promise.reject({ response: { data: { message: "Model chwilowo niedostępny" } } }));
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Wygeneruj i porównaj dwa opisy" }));
    expect(await screen.findByText("Zapisany opis Gemmy")).toBeTruthy();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Model chwilowo niedostępny");
    await waitFor(() => expect(screen.getByRole("button", { name: "Wygeneruj opis — Mistral Small 4" })).toHaveProperty("disabled", false));
  });

  it("saves user knowledge with a revision and retains generated descriptions", async () => {
    vi.mocked(axios.post).mockResolvedValue(result(gemma, "Opis obrazu"));
    vi.mocked(axios.patch).mockResolvedValue({ data: { photo: { ...initial, user_description: "Dzieci z grupy Filipa", user_description_revision: 2 } } });
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Wygeneruj opis — Gemma 4 31B" }));
    await screen.findByText("Opis obrazu");
    fireEvent.change(screen.getByLabelText("Twój opis zdjęcia"), { target: { value: "Dzieci z grupy Filipa" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz swój opis" }));
    await screen.findByText("Zapisano opis.");
    expect(axios.patch).toHaveBeenCalledWith("/api/contacts/493/photo/description", {
      storage_key: "photo.png", user_description: "Dzieci z grupy Filipa", user_description_revision: 1,
    }, expect.anything());
    expect(screen.getByText("Opis obrazu")).toBeTruthy();
  });
});
