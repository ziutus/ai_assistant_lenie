import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ContentGroups from "./contentGroups";

vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas:5000", apiKey: "test-key" }) };
});

const topics = [
  { id: 1, name: "AI", kind: "topic", retention_months: null, saved_item_count: 2, document_count: 40, chunk_count: 5, provenance_item_count: 9 },
  { id: 2, name: "Agenci AI", kind: "topic", retention_months: 12, saved_item_count: 0, document_count: 3, chunk_count: 0, provenance_item_count: 0 },
  { id: 3, name: "Żółwie", kind: "topic", retention_months: null, saved_item_count: 0, document_count: 0, chunk_count: 0, provenance_item_count: 0 },
  { id: 9, name: "Pilne", kind: "priority", retention_months: null, saved_item_count: 0, document_count: 0, chunk_count: 0, provenance_item_count: 0 },
];
const json = (body: object, status = 200) => new Response(JSON.stringify(body), { status });
const calls = () => vi.mocked(fetch).mock.calls as unknown as [string, RequestInit | undefined][];
const sent = (method: string) => calls().find(([, init]) => init?.method === method);

const retention = { default_months: 6, saved: false, built_in_months: 6, min: 1, max: 120 };
// GET answers every page load; a test overrides only the write it exercises.
const base = (url: string, init?: RequestInit): Response => {
  if (url.endsWith("/feed_items/retention") && !init?.method) return json(retention);
  if (url.endsWith("/content_groups") && !init?.method) return json({ content_groups: topics });
  return json({}, 200);
};
let respond: (url: string, init?: RequestInit) => Response;
beforeEach(() => {
  respond = base;
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(respond(url, init))));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

// A topic name also appears as an <option> in every merge select, so match the row's own <strong> label.
const row = async (name: string) => (await screen.findByText(name, { selector: "strong" })).closest("tr") as HTMLElement;

const hierarchy = () => {
  respond = (url, init) => url.endsWith("/content_groups") && !init?.method
    ? json({ content_groups: topics.map(topic => ({ ...topic, parent_id: topic.id === 2 ? 1 : topic.id === 3 ? 2 : null })) })
    : base(url, init);
};

it("shows depth-first tree order and keeps indentation when filtering", async () => {
  hierarchy();
  render(<ContentGroups />);
  const child = await row("Agenci AI");
  expect(screen.getAllByRole("row").slice(1).map(entry => entry.querySelector("strong")?.textContent)).toEqual(["AI", "Agenci AI", "Żółwie"]);
  expect(child.querySelector("td")?.style.paddingLeft).toBe("20px");
  expect((await row("Żółwie")).querySelector("td")?.style.paddingLeft).toBe("40px");
  fireEvent.change(screen.getByLabelText("Szukaj:"), { target: { value: "zolw" } });
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect((await row("Żółwie")).querySelector("td")?.style.paddingLeft).toBe("40px");
});

it("does not offer self, descendants or level-three topics as parents", async () => {
  hierarchy();
  render(<ContentGroups />);
  await row("AI");
  expect(within(screen.getByLabelText("Temat nadrzędny dla AI")).getAllByRole("option")).toHaveLength(1);
  expect(within(screen.getByLabelText("Pod tematem:")).queryByRole("option", { name: "Żółwie" })).toBeNull();
});

it("saves a parent draft with PATCH", async () => {
  render(<ContentGroups />);
  const child = await row("Agenci AI");
  fireEvent.change(screen.getByLabelText("Temat nadrzędny dla Agenci AI"), { target: { value: "1" } });
  expect(sent("PATCH")).toBeUndefined();
  fireEvent.click(within(child).getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("status")).textContent).toBe("Temat „Agenci AI” jest teraz podtematem „AI”.");
  expect(sent("PATCH")?.[0]).toBe("http://nas:5000/content_groups/2");
  expect(JSON.parse(String(sent("PATCH")?.[1]?.body))).toEqual({ parent_id: 1 });
});

it("clears a parent and can cancel a draft", async () => {
  hierarchy();
  render(<ContentGroups />);
  const child = await row("Agenci AI");
  const select = screen.getByLabelText("Temat nadrzędny dla Agenci AI") as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "" } });
  fireEvent.click(within(child).getByRole("button", { name: "Anuluj" }));
  expect(select.value).toBe("1");
  expect(sent("PATCH")).toBeUndefined();
  fireEvent.change(select, { target: { value: "" } });
  fireEvent.click(within(child).getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("status")).textContent).toBe("Temat „Agenci AI” jest tematem głównym.");
  expect(JSON.parse(String(sent("PATCH")?.[1]?.body))).toEqual({ parent_id: null });
});

it("creates a sub-topic with parent_id", async () => {
  respond = (url, init) => init?.method === "POST" ? json({}, 201) : base(url, init);
  render(<ContentGroups />);
  await row("AI");
  fireEvent.change(screen.getByLabelText("Nowy temat:"), { target: { value: "Modele" } });
  fireEvent.change(screen.getByLabelText("Pod tematem:"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj temat" }));
  await screen.findByRole("status");
  expect(JSON.parse(String(sent("POST")?.[1]?.body))).toEqual({ name: "Modele", kind: "topic", parent_id: 1 });
});

it.each([
  ["a topic cannot be its own ancestor", "Temat nie może być swoim własnym przodkiem."],
  ["topic hierarchy is limited to 3 levels", "Hierarchia może mieć najwyżej 3 poziomy."],
  ["parent must be an active topic", "Temat nadrzędny musi być aktywnym tematem."],
])("translates hierarchy error %s", async (message, translated) => {
  respond = (url, init) => init?.method === "PATCH" ? json({ message }, 400) : base(url, init);
  render(<ContentGroups />);
  const child = await row("Agenci AI");
  fireEvent.change(screen.getByLabelText("Temat nadrzędny dla Agenci AI"), { target: { value: "1" } });
  fireEvent.click(within(child).getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("alert")).textContent).toBe(translated);
});

it("lists only topics with their usage and allows deleting only an unused one", async () => {
  render(<ContentGroups />);
  const ai = await row("AI");
  expect(screen.queryByText("Pilne")).toBeNull();
  expect(within(ai).getByText("40")).toBeTruthy();
  expect((within(ai).getByRole("button", { name: "Usuń" }) as HTMLButtonElement).disabled).toBe(true);
  expect((within(await row("Żółwie")).getByRole("button", { name: "Usuń" }) as HTMLButtonElement).disabled).toBe(false);
});

it("renames a topic in place and says it applies to every tagged item", async () => {
  respond = (url, init) => init?.method === "PATCH" ? json({ id: 1, name: "AI – ogólnie" }) : base(url, init);
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
  respond = (url, init) => init?.method === "PATCH" ? json({ message: "active group name already exists" }, 409) : base(url, init);
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
    ? json({ moved: { documents: 40, chunks: 5, feed_items: 9 } }) : base(url, init);
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
  respond = (url, init) => init?.method === "POST" ? json({ id: 10, name: "Smart home" }, 201) : base(url, init);
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

it("shows each topic's validity and the default, and saves a topic's own validity", async () => {
  respond = (url, init) => init?.method === "PATCH" ? json({ id: 1, retention_months: 12 }) : base(url, init);
  render(<ContentGroups />);
  const ai = await row("AI");
  expect((await screen.findByLabelText("Domyślnie (mies.):") as HTMLInputElement).value).toBe("6");
  expect((within(await row("Agenci AI")).getByRole("spinbutton") as HTMLInputElement).value).toBe("12");
  const input = within(ai).getByRole("spinbutton") as HTMLInputElement;
  expect(input.placeholder).toBe("6");
  fireEvent.change(input, { target: { value: "12" } });
  fireEvent.click(within(ai).getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("status")).textContent).toContain("„AI”: wpisy „Może kiedyś” ważne 12 mies.");
  const patch = sent("PATCH");
  expect(patch?.[0]).toBe("http://nas:5000/content_groups/1");
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ retention_months: 12 });
});

it("clearing a topic's validity sends null so the default applies", async () => {
  respond = (url, init) => init?.method === "PATCH" ? json({ id: 2 }) : base(url, init);
  render(<ContentGroups />);
  const agents = await row("Agenci AI");
  fireEvent.change(within(agents).getByRole("spinbutton"), { target: { value: "" } });
  fireEvent.click(within(agents).getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("status")).textContent).toContain("używa ważności domyślnej");
  expect(JSON.parse(String(sent("PATCH")?.[1]?.body))).toEqual({ retention_months: null });
});

it("saves a topic description with PATCH only after the draft changes", async () => {
  respond = (url, init) => init?.method === "PATCH" ? json({ id: 3, description: "Zakres" }) : base(url, init);
  render(<ContentGroups />);
  const turtles = await row("Żółwie");
  expect(within(turtles).queryByRole("button", { name: "Zapisz" })).toBeNull();
  fireEvent.change(within(turtles).getByLabelText("Opis tematu Żółwie"), { target: { value: " Zakres " } });
  expect(sent("PATCH")).toBeUndefined();
  fireEvent.click(within(turtles).getByRole("button", { name: "Zapisz" }));
  expect((await screen.findByRole("status")).textContent).toContain("Zapisano opis tematu „Żółwie”");
  expect(sent("PATCH")?.[0]).toBe("http://nas:5000/content_groups/3");
  expect(JSON.parse(String(sent("PATCH")?.[1]?.body))).toEqual({ description: "Zakres" });
});

it("saves the household default validity", async () => {
  respond = (url, init) => init?.method === "PUT" ? json({ default_months: 9, saved: true }) : base(url, init);
  render(<ContentGroups />);
  const field = await screen.findByLabelText("Domyślnie (mies.):");
  fireEvent.change(field, { target: { value: "9" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz domyślną" }));
  expect((await screen.findByRole("status")).textContent).toContain("Domyślna ważność wpisów „Może kiedyś”: 9 mies.");
  expect(JSON.parse(String(sent("PUT")?.[1]?.body))).toEqual({ default_months: 9 });
});

it("previews what has expired and moves it only after the second click", async () => {
  const due = { dry_run: true, due: 2, expired: 0, items: [{ id: 5, title: "Stary wpis", saved_at: "2026-01-02T00:00:00+00:00", expires_at: "2026-07-02T00:00:00+00:00", months: 6 }] };
  respond = (url, init) => {
    if (init?.method === "POST" && url.endsWith("/expire_saved")) return json(JSON.parse(String(init.body)).dry_run ? due : { dry_run: false, due: 2, expired: 2, items: [] });
    return base(url, init);
  };
  render(<ContentGroups />);
  await row("AI");
  fireEvent.click(screen.getByRole("button", { name: "Sprawdź, co wygasło" }));
  expect(await screen.findByText(/Stary wpis/)).toBeTruthy();
  expect(calls().filter(([, init]) => init?.method === "POST" && !JSON.parse(String(init.body)).dry_run)).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: /Przesuń 2 do „Pomiń” teraz/ }));
  expect((await screen.findByRole("status")).textContent).toContain("Przesunięto do „Pomiń”: 2 z 2 wpisów.");
});
