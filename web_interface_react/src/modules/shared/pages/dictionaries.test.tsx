import axios from "axios";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Dictionaries from "./dictionaries";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/ner_channel_glossary")) return { data: { status: "success", entries: [], authors: ["Kanał X"] } };
    return { data: { status: "success", rules: [], total: 0 } };
  });
});
afterEach(cleanup);

const open = (url: string) => render(<MemoryRouter initialEntries={[url]}><Dictionaries /></MemoryRouter>);

it("opens on the channel glossary and switches to the region and phrase dictionaries", async () => {
  open("/dictionaries");
  expect((await screen.findByRole("heading", { name: /Słownik nazw kanału/ }))).toBeTruthy();
  expect(screen.getByRole("tab", { name: "Kanał" }).getAttribute("aria-selected")).toBe("true");

  fireEvent.click(screen.getByRole("tab", { name: "Region" }));
  expect(await screen.findByLabelText("Region")).toBeTruthy();
  expect(screen.getByRole("tab", { name: "Region" }).getAttribute("aria-selected")).toBe("true");
  expect(vi.mocked(axios.get).mock.calls.some(([url, config]) =>
    String(url).endsWith("/transcript_corrections") && (config?.params as { scope?: string })?.scope === "region")).toBe(true);

  fireEvent.click(screen.getByRole("tab", { name: "Frazy" }));
  expect(await screen.findByLabelText("Zakres reguły")).toBeTruthy();
});

it("honours ?tab= from the address and falls back to the channel tab for an unknown value", async () => {
  open("/dictionaries?tab=region");
  expect((await screen.findByLabelText("Region"))).toBeTruthy();
  cleanup();
  open("/dictionaries?tab=nonsense");
  expect(screen.getByRole("tab", { name: "Kanał" }).getAttribute("aria-selected")).toBe("true");
});
