import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ContactFacts from "./ContactFacts";

vi.mock("axios");
afterEach(cleanup);
const claim = (id: number, overrides = {}) => ({
  id, source_key: "facebook", value: { year: 1986, month: 9, day: 26 }, status: "candidate",
  observed_at: "2026-09-29T12:00:00Z", last_seen_at: "2026-09-30T12:00:00Z", ...overrides,
});
const tonn = () => [{ id: 1, attribute_key: "birthday", resolution_mode: "auto", selected_assertion_id: 97,
  assertions: [claim(304, { status: "rejected", evidence_note: "Na FB data 26 września 1986. Rok 1986 jest fałszywy.",
    source_url: "https://www.facebook.com/tonn", review_note: "Rok zmyślony", reviewed_by: "owner", reviewed_at: "2026-09-30T12:00:00Z" }),
  claim(97, { source_key: "legacy_unknown", status: "confirmed", value: { year: null, month: 9, day: 26 }, observed_at: "2025-01-01T12:00:00Z" })],
}];
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockResolvedValue({ data: { facts: tonn() } });
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
});
const setup = (editable = false, onChanged = vi.fn()) => render(<ContactFacts contactId="263" editable={editable} onChanged={onChanged} />);

it("shows Tonn's selected birthday and rejected Facebook year with notes and review", async () => {
  setup();
  const rows = within(await screen.findByRole("table")).getAllByRole("row").slice(1);
  expect(rows).toHaveLength(2);
  expect(rows[0].textContent).toContain("26.09 (bez roku)");
  expect(rows[0].textContent).toContain("✓ Widocznaautomatyczna");
  expect(rows[0].textContent).toContain("Dane sprzed śledzenia źródeł");
  expect(rows[1].textContent).toContain("26.09.1986");
  expect(rows[1].textContent).toContain("Odrzucona");
  expect(rows[1].textContent).toContain("Rok 1986 jest fałszywy.");
  expect(rows[1].textContent).toContain("Przegląd: Rok zmyślony");
  expect(rows[1].textContent).toContain("owner");
  expect(within(rows[1]).queryByText("✓ Widoczna")).toBeNull();
  expect(screen.getByText("Tez: 2, odrzuconych: 1")).toBeTruthy();
  const link = screen.getByRole("link", { name: "Facebook" });
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  const observed = within(rows[1]).getByText("29.09.2026");
  expect(observed.title).toContain("Ostatnio widziano: 30.09.2026");
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.getAllByRole("columnheader").every(th => th.getAttribute("scope") === "col")).toBe(true);
});

it("groups attributes and sorts selected claims first, then newest observations", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { facts: [
    { id: 4, attribute_key: "hometown", assertions: [claim(4, { value: { hometown: "Kraków" } })] },
    { id: 5, attribute_key: "education", assertions: [claim(5, { value: { institution: "UJ" } })] },
    { id: 3, attribute_key: "current_city", assertions: [claim(3, { value: { current_city: "Łódź" } })] },
    { id: 2, attribute_key: "gender", assertions: [claim(2, { value: { gender: "male" } })] },
    { ...tonn()[0], assertions: [...tonn()[0].assertions, claim(305, { source_key: "linkedin", observed_at: "2026-09-30T12:00:00Z" })] },
  ] } });
  setup();
  const rows = within(await screen.findByRole("table")).getAllByRole("row").slice(1);
  expect(rows.map(row => within(row).getAllByRole("cell")[0].textContent)).toEqual([
    "Data urodzenia", "Data urodzenia", "Data urodzenia", "Płeć", "Obecne miasto", "Miejscowość rodzinna", "Wykształcenie",
  ]);
  expect(rows[1].textContent).toContain("LinkedIn");
  expect(rows[2].textContent).toContain("Facebook");
  for (const value of ["mężczyzna", "Łódź", "Kraków", "UJ"]) expect(screen.getByText(value)).toBeTruthy();
});

it("renders nothing when there are no assertions", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { facts: [{ assertions: [] }] } });
  const { container } = setup();
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
  expect(container.innerHTML).toBe("");
});

it("formats partial birthdays without inventing missing parts", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { facts: [{ ...tonn()[0], assertions: [
    claim(1, { value: { year: 1986, month: null, day: null } }),
    claim(2, { value: { year: null, month: 9, day: null } }),
    claim(3, { value: { year: null, month: null, day: null } }),
  ] }] } });
  setup();
  expect(await screen.findByText("1986 (bez dnia i miesiąca)")).toBeTruthy();
  expect(screen.getByText("??.09 (bez roku)")).toBeTruthy();
});

it.each([['Potwierdź', 'confirmed'], ['Otwórz ponownie', 'candidate']])(
  "sends %s without a reason", async (label, status) => {
    const onChanged = vi.fn();
    setup(true, onChanged);
    const row = (await screen.findByText("Odrzucona")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: label }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(axios.patch).toHaveBeenCalledWith("/contacts/263/facts/assertions/304", { status }, expect.anything());
  },
);

it("offers status-specific controls only for non-manual assertions in edit mode", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { facts: [{ ...tonn()[0], assertions: [
    claim(1, { source_key: "user_manual" }), claim(2, { source_key: "custom_source" }), ...tonn()[0].assertions,
  ] }] } });
  setup(true);
  const manual = (await screen.findByText("Ręcznie (użytkownik)")).closest("tr")!;
  expect(within(manual).queryByRole("button")).toBeNull();
  expect(within(manual).getByTitle("Wartość wpisana ręcznie - edytuj pole kontaktu")).toBeTruthy();
  const candidate = screen.getByText("custom_source").closest("tr")!;
  expect(within(candidate).getByRole("button", { name: "Potwierdź" })).toBeTruthy();
  expect(within(candidate).queryByRole("button", { name: "Otwórz ponownie" })).toBeNull();
  const rejected = screen.getByText("Odrzucona").closest("tr")!;
  expect(within(rejected).queryByRole("button", { name: "Odrzuć..." })).toBeNull();
  expect(within(rejected).getByRole("button", { name: "Otwórz ponownie" })).toBeTruthy();
});

it("rejects with note and refreshes assertions and parent", async () => {
  const onChanged = vi.fn();
  setup(true, onChanged);
  fireEvent.click(await screen.findByRole("button", { name: "Odrzuć..." }));
  fireEvent.change(screen.getByLabelText("Powód odrzucenia"), { target: { value: " Błędna data " } });
  vi.mocked(axios.get).mockResolvedValue({ data: { facts: [{ ...tonn()[0], selected_assertion_id: null,
    assertions: [claim(97, { status: "rejected", review_note: "Błędna data" })] }] } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz odrzucenie" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  expect(axios.patch).toHaveBeenCalledWith("/contacts/263/facts/assertions/97",
    { status: "rejected", note: "Błędna data" }, { headers: { "x-api-key": "undefined" } });
  expect(axios.get).toHaveBeenCalledTimes(2);
  expect(screen.getByText("Przegląd: Błędna data")).toBeTruthy();
  expect(screen.queryByText("✓ Widoczna")).toBeNull();
});

it("shows Polish fetch and review errors and retains the rejection reason", async () => {
  vi.mocked(axios.patch).mockRejectedValueOnce(new Error("Network error"));
  const onChanged = vi.fn();
  setup(true, onChanged);
  fireEvent.click(await screen.findByRole("button", { name: "Odrzuć..." }));
  fireEvent.change(screen.getByLabelText("Powód odrzucenia"), { target: { value: "Powód" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz odrzucenie" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Nie udało się zapisać");
  expect(screen.getByLabelText("Powód odrzucenia")).toHaveProperty("value", "Powód");
  expect(onChanged).not.toHaveBeenCalled();
  cleanup();
  vi.mocked(axios.get).mockRejectedValueOnce(new Error("Network error"));
  setup();
  expect((await screen.findByRole("alert")).textContent).toBe("Nie udało się pobrać faktów i źródeł.");
});
