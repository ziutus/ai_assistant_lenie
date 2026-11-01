import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import FeedReviewReasons from "./feedReviewReasons";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas:5000", apiKey: "test-key" }) };
});

const custom = { code: "custom", label: "Własny powód", sort_order: 10, system: false, active: true, selectable: true, usage_count: 0 };
const system = { ...custom, code: "expired", label: "Wygasło", system: true, selectable: false, usage_count: 3 };
const json = (body: object, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (_url, init) => json(init?.method === "GET" ? { reasons: [custom, system] } : { status: "success" })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("lists counts, protects system fields and edits labels/order", async () => {
  render(<FeedReviewReasons />);
  const row = (await screen.findByText("Własny powód")).closest("tr")!;
  const systemRow = screen.getByText(/expired/).closest("tr")!;
  expect(within(systemRow).getByRole("checkbox", { name: "Aktywny expired" })).toHaveProperty("disabled", true);
  expect(within(systemRow).getByRole("checkbox", { name: "Wybieralny expired" })).toHaveProperty("disabled", true);
  expect(within(systemRow).queryByRole("button", { name: "Usuń" })).toBeNull();
  expect(within(systemRow).getByText("3")).toBeTruthy();
  fireEvent.click(within(row).getByRole("button", { name: "Edytuj" }));
  fireEvent.change(screen.getByLabelText("Etykieta custom"), { target: { value: "Nowa etykieta" } });
  fireEvent.change(screen.getByLabelText("Kolejność custom"), { target: { value: "25" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  await screen.findByRole("button", { name: "Dodaj powód" });
  expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith("/custom") && init?.method === "PATCH"
    && init.body === JSON.stringify({ label: "Nowa etykieta", sort_order: 25 }))).toBe(true);
});

it("adds a reason and requires a second click to delete", async () => {
  render(<FeedReviewReasons />);
  const row = (await screen.findByText("Własny powód")).closest("tr")!;
  fireEvent.click(within(row).getByRole("button", { name: "Usuń" }));
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Anuluj usunięcie" }));
  fireEvent.click(within(row).getByRole("button", { name: "Usuń" }));
  fireEvent.click(screen.getByRole("button", { name: "Potwierdź usunięcie" }));
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true);
  await screen.findByRole("button", { name: "Usuń" });
  fireEvent.change(screen.getByLabelText("Kod nowego powodu"), { target: { value: "new_reason" } });
  fireEvent.change(screen.getByLabelText("Etykieta nowego powodu"), { target: { value: "Nowy" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj powód" }));
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "POST"
    && init.body === JSON.stringify({ code: "new_reason", label: "Nowy", sort_order: 100 }))).toBe(true);
});

it("explains service-key errors in Polish and includes request details", async () => {
  vi.mocked(fetch).mockImplementation(async (_url, init) => init?.method === "GET"
    ? json({ reasons: [custom] }) : json({}, 403));
  vi.spyOn(console, "error").mockImplementation(() => {});
  render(<FeedReviewReasons />);
  await screen.findByText("Własny powód");
  fireEvent.click(screen.getByRole("checkbox", { name: "Aktywny custom" }));
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("wymaga klucza service");
  expect(alert.textContent).toContain("PATCH http://nas:5000/feed_review_reasons/custom");
  expect(screen.getByRole("checkbox", { name: "Aktywny custom" })).toHaveProperty("checked", true);
});

it("toggles selectable and active independently", async () => {
  render(<FeedReviewReasons />);
  await screen.findByText("Własny powód");
  fireEvent.click(screen.getByRole("checkbox", { name: "Wybieralny custom" }));
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.body === JSON.stringify({ selectable: false }))).toBe(true);
});
