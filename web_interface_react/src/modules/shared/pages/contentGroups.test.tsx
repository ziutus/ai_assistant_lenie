import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ContentGroups from "./contentGroups";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas:5000", apiKey: "test-key" }) };
});

const topics = [
  { id: 1, name: "AI", kind: "topic", saved_item_count: 2, document_count: 40, chunk_count: 5, provenance_item_count: 9 },
  { id: 2, name: "Agenci AI", kind: "topic", saved_item_count: 0, document_count: 3, chunk_count: 0, provenance_item_count: 0 },
  { id: 3, name: "Żółwie", kind: "topic", saved_item_count: 0, document_count: 0, chunk_count: 0, provenance_item_count: 0 },
  { id: 9, name: "Pilne", kind: "priority", saved_item_count: 0, document_count: 0, chunk_count: 0, provenance_item_count: 0 },
];
const json = (body: object, status = 200) => new Response(JSON.stringify(body), { status });
const calls = () => vi.mocked(fetch).mock.calls as unknown as [string, RequestInit | undefined][];
const sent = (method: string) => calls().find(([, init]) => init?.method === method);

let respond: (url: string, init?: RequestInit) => Response;
beforeEach(() => {
  respond = (url, init) => {
    if (url.endsWith("/content_groups") && !init?.method) return json({ content_groups: topics });
    return json({}, 200);
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(respond(url, init))));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

// A topic name also appears as an <option> in every merge select, so match the row's own <strong> label.
const row = async (name: string) => (await screen.findByText(name, { selector: "strong" })).closest("tr") as HTMLElement;

it("lists only topics with their usage and allows deleting only an unused one", async () => {
  render(<ContentGroups />);
  const ai = await row("AI");
  expect(screen.queryByText("Pilne")).toBeNull();
  expect(within(ai).getByText("40")).toBeTruthy();
  expect((within(ai).getByRole("button", { name: "Usuń" }) as HTMLButtonElement).disabled).toBe(true);
  expect((within(await row("Żółwie")).getByRole("button", { name: "Usuń" }) as HTMLButtonElement).disabled).toBe(false);
});

it("renames a topic in place and says it applies to every tagged item", async () => {
  respond = (url, init) => init?.method === "PATCH" ? json({ id: 1, name: "AI – ogólnie" }) : json({ content_groups: topics });
  render(<ContentGroups />);
  fireEvent.click(within(await row("AI")).getByRole("button", { name: "Zmień nazwę" }));
  fireEvent.change(screen.getByLabelText("Nowa nazwa tematu AI"), { target: { value: "AI – ogólnie" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("status")).textContent).toContain("„AI” na „AI – ogólnie”");
  const patch = sent("PATCH");
  expect(patch?.[0]).toBe("http://nas:5000/content_groups/1");
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ name: "AI – ogólnie" });
});

it("explains a name conflict in Polish", async () => {
  respond = (url, init) => init?.method === "PATCH" ? json({ message: "active group name already exists" }, 409) : json({ content_groups: topics });
  render(<ContentGroups />);
  fireEvent.click(within(await row("AI")).getByRole("button", { name: "Zmień nazwę" }));
  fireEvent.change(screen.getByLabelText("Nowa nazwa tematu AI"), { target: { value: "Agenci AI" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("alert")).textContent).toContain("już istnieje");
});

it("deletes an unused topic only after a second confirmation", async () => {
  render(<ContentGroups />);
  fireEvent.click(within(await row("Żółwie")).getByRole("button", { name: "Usuń" }));
  expect(sent("DELETE")).toBeUndefined();
  fireEvent.click(screen.getByRole("button", { name: "Tak, usuń" }));
  await waitFor(() => expect(sent("DELETE")?.[0]).toBe("http://nas:5000/content_groups/3"));
  expect((await screen.findByRole("status")).textContent).toContain("Usunięto temat „Żółwie”");
});

it("merges a used topic into another after confirmation and reports what moved", async () => {
  respond = (url, init) => init?.method === "POST" && url.endsWith("/merge")
    ? json({ moved: { documents: 40, chunks: 5, feed_items: 9 } }) : json({ content_groups: topics });
  render(<ContentGroups />);
  const ai = await row("AI");
  fireEvent.change(within(ai).getByLabelText("Scal „AI” z…"), { target: { value: "2" } });
  fireEvent.click(within(ai).getByRole("button", { name: "Scal" }));
  expect(screen.getByText(/Przenieść 40 dok\., 5 fragm\., 9 wpisów feedu do „Agenci AI”/)).toBeTruthy();
  expect(sent("POST")).toBeUndefined();
  fireEvent.click(screen.getByRole("button", { name: "Tak, scal" }));
  expect((await screen.findByRole("status")).textContent).toContain("przeniesiono 40 dok., 5 fragm., 9 wpisów feedu");
  const post = sent("POST");
  expect(post?.[0]).toBe("http://nas:5000/content_groups/1/merge");
  expect(JSON.parse(String(post?.[1]?.body))).toEqual({ target_id: 2 });
});

it("adds a topic", async () => {
  respond = (url, init) => init?.method === "POST" ? json({ id: 10, name: "Smart home" }, 201) : json({ content_groups: topics });
  render(<ContentGroups />);
  await row("AI");
  fireEvent.change(screen.getByLabelText("Nowy temat:"), { target: { value: " Smart home " } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj temat" }));
  expect((await screen.findByRole("status")).textContent).toContain("Dodano temat „Smart home”");
  expect(JSON.parse(String(sent("POST")?.[1]?.body))).toEqual({ name: "Smart home", kind: "topic" });
});

it("filters ignoring diacritics", async () => {
  render(<ContentGroups />);
  await row("AI");
  fireEvent.change(screen.getByLabelText("Szukaj:"), { target: { value: "zolw" } });
  expect(screen.getByText("Żółwie", { selector: "strong" })).toBeTruthy();
  expect(screen.queryByText("Agenci AI", { selector: "strong" })).toBeNull();
});
