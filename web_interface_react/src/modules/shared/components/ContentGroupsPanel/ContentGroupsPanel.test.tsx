import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ContentGroupsPanel from "./ContentGroupsPanel";

vi.mock("../../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "http://nas", apiKey: "key" }) };
});
const json = (body: object, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it("replaces an old Bielik run once, hides stale suggestions and does not retry a chosen-model error", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const model = "openrouter/google/gemini-2.5-flash-lite";
  let status = "completed";
  let runModel = "Bielik";
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/content_groups")) return json({ content_groups: [{ id: 1, name: "AI", kind: "topic" }] });
    if (url.endsWith("/groups")) return json({ groups: [] });
    if (init?.method === "POST") { runModel = model; status = "queued"; return json({ run: { status } }); }
    return json({ run: { model: runModel, status }, suggestions: [{ id: 3, group_id: 1, confidence: 0.9, status: "pending" }] });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<ContentGroupsPanel feedItemId={7} autoSuggest suggestModel={model} />);
  await screen.findByText("🤖 Szukam kategorii…");
  expect(screen.queryByText(/Sugestia:/)).toBeNull();
  const posts = () => fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts()).toHaveLength(1);
  expect(posts()[0][1]?.body).toBe(JSON.stringify({ model }));
  status = "error";
  await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
  expect(posts()).toHaveLength(1);
  expect(screen.queryByText("🤖 Szukam kategorii…")).toBeNull();
  fireEvent.click(screen.getByText("Podpowiedz ponownie"));
  await waitFor(() => expect(posts()).toHaveLength(2));
  expect(posts()[1][1]?.body).toBe(JSON.stringify({ model, force: true }));
});

it.each([false, true])("accepts a proposed topic and preserves topics and priority (conflict: %s)", async conflict => {
  const topic = { id: 2, name: "Żółwie", kind: "topic" };
  const current = [{ id: 1, name: "AI", kind: "topic" }, { id: 10, name: "Pilne", kind: "priority" }];
  let created = false;
  const onSaved = vi.fn();
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/content_groups")) {
      if (init?.method === "POST") { created = true; return json(topic, conflict ? 409 : 200); }
      return json({ content_groups: [...current, ...(created ? [topic] : [])] });
    }
    if (url.endsWith("/groups")) return json({ groups: init?.method === "PATCH" ? [...current, topic] : current });
    return json({ run: { model: "Gemini", status: "completed" }, suggestions: [], new_topics: [{ name: "Żółwie", confidence: 0.9, reason: "Opieka" }] });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<ContentGroupsPanel feedItemId={7} onSaved={onSaved} />);
  await screen.findByText("Nowy temat: Żółwie (90%) — Opieka");
  fireEvent.click(screen.getByText("Utwórz i dodaj"));
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith([...current, topic]));
  expect(fetcher.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body).toBe(JSON.stringify({ name: "Żółwie", kind: "topic" }));
  expect(fetcher.mock.calls.find(([, init]) => init?.method === "PATCH")?.[1]?.body).toBe(JSON.stringify({ group_ids: [1, 2, 10] }));
  expect(screen.queryByText(/Nowy temat:/)).toBeNull();
});

it("dismisses proposals locally", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json({ groups: [], content_groups: [], suggestions: [], new_topics: [{ name: "Nowy", confidence: 0.8, reason: "Opis" }] })));
  render(<ContentGroupsPanel feedItemId={7} />);
  fireEvent.click(await screen.findByText("Odrzuć"));
  expect(screen.queryByText(/Nowy temat:/)).toBeNull();
});
