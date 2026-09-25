import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ContactFamilyForm from "./ContactFamilyForm";

vi.mock("axios");
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

const setup = () => render(<ContactFamilyForm contactId="493" contactName="Anna" apiUrl="/api" apiKey="test"
  photo={{ id: "shared-photo", subject_kind: "people", people_count: 3, classification_revision: 1,
    storage_key: "photo.png", user_description: "Mąż i dzieci — bliźnięta.", user_description_revision: 1, ai_descriptions: {} }}
  groups={[]} onCreated={vi.fn()} />);

it("creates distinct unnamed children and twins only when the user marks that fact", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { family: { spouse: { id: 1, display_name: "Drugi rodzic — Anna" }, children: [
    { id: 2, display_name: "Dziecko 1 — Anna" }, { id: 3, display_name: "Dziecko 2 — Anna" },
  ] } } });
  setup();
  fireEvent.click(screen.getByRole("button", { name: "Utwórz kontakty członków rodziny" }));
  expect(screen.getByLabelText("Wiem, że te dzieci są bliźniętami")).toHaveProperty("checked", false);
  fireEvent.click(screen.getByLabelText("Wiem, że te dzieci są bliźniętami"));
  fireEvent.click(screen.getByRole("button", { name: "Utwórz rodzinę i powiązania" }));
  await screen.findByText("Zapisano rodzinę i powiązania.");
  const body: any = vi.mocked(axios.post).mock.calls[0][1];
  expect(body.children).toEqual([
    { first_name: "", last_name: "", display_label: "Dziecko 1 — Anna" },
    { first_name: "", last_name: "", display_label: "Dziecko 2 — Anna" },
  ]);
  expect(body.twins).toBe(true);
  expect(body.children_group_id).toBeNull();
  expect(screen.getByRole("link", { name: "Dziecko 2 — Anna" }).getAttribute("href")).toBe("/contacts/3");
});

it("reuses the request ID after an uncertain network result", async () => {
  vi.mocked(axios.post).mockRejectedValue(new Error("connection lost"));
  setup();
  fireEvent.click(screen.getByRole("button", { name: "Utwórz kontakty członków rodziny" }));
  fireEvent.click(screen.getByRole("button", { name: "Utwórz rodzinę i powiązania" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Utwórz rodzinę i powiązania" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
  const calls = vi.mocked(axios.post).mock.calls;
  expect((calls[0][1] as any).request_id).toBe((calls[1][1] as any).request_id);
});
