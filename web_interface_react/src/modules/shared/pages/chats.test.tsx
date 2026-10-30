import axios from "axios";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthorizationContext } from "../context/authorizationContext";
import Chats from "./chats";

vi.mock("axios");
afterEach(cleanup);

const conversation = (id: number, name: string, extra = {}) => ({
  id, platform: "whatsapp", chat_key: `k${id}`, display_name: name, message_count: 0, last_imported_at: null,
  community_group_id: null, community_name: null, is_community: false, is_announce: false, ...extra,
});

function mockApi(conversations: unknown[]) {
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/chat_conversations")) return { data: { conversations, total: conversations.length } };
    if (url.endsWith("/whatsapp_sync/status")) {
      return { data: { configured: false, connection_state: "unknown", bridge_reachable: false, needs_pairing: false,
        last_success_at: null, last_error: null, last_error_at: null, enabled_chats: 0,
        media: { pending: 0, unavailable: 0, error: 0 } } };
    }
    return { data: { chats: [], groups: [] } };
  });
}

function renderChats() {
  const value = { apiKey: "k", apiUrl: "http://api" } as never;
  return render(
    <MemoryRouter><AuthorizationContext.Provider value={value}><Chats /></AuthorizationContext.Provider></MemoryRouter>,
  );
}

beforeEach(() => vi.resetAllMocks());

it("groups conversations under their community, umbrella and announcements first", async () => {
  mockApi([
    conversation(1, "AI Jam - ogród", { community_group_id: 10, community_name: "AI Jam Łódź" }),
    conversation(2, "AI Jam - ogłoszenia", { community_group_id: 10, community_name: "AI Jam Łódź", is_announce: true }),
    conversation(3, "AI Jam Łódź", { community_group_id: 10, community_name: "AI Jam Łódź", is_community: true }),
    conversation(4, "Zwykła grupa"),
  ]);
  renderChats();

  const header = await screen.findByRole("heading", { name: "AI Jam Łódź" });
  const rows = screen.getAllByRole("link").filter((a) => a.getAttribute("href")?.startsWith("/chats/"));
  expect(rows.map((a) => a.textContent)).toEqual(["AI Jam Łódź", "AI Jam - ogłoszenia", "AI Jam - ogród", "Zwykła grupa"]);
  expect(screen.getByText("— Społeczność")).toBeTruthy();
  expect(screen.getByText("— Ogłoszenia")).toBeTruthy();
  // community rows sit under their header, plain conversations under "Pozostałe rozmowy"
  const other = screen.getByText("Pozostałe rozmowy");
  expect(header.compareDocumentPosition(rows[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(rows[2].compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(other.compareDocumentPosition(rows[3]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("keeps the flat list when no conversation belongs to a community", async () => {
  mockApi([conversation(1, "Ala"), conversation(2, "Bartek")]);
  renderChats();
  await waitFor(() => expect(screen.getByText("Ala")).toBeTruthy());
  expect(screen.queryByText("Pozostałe rozmowy")).toBeNull();
  expect(screen.queryByText(/Społeczność WhatsApp/)).toBeNull();
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
});
