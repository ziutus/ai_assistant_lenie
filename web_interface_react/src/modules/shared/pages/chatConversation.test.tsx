import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthorizationContext } from "../context/authorizationContext";
import ChatConversation from "./chatConversation";

vi.mock("axios");
afterEach(cleanup);

const CONVERSATION = { id: 6, platform: "whatsapp", chat_key: "k", display_name: "Dom - ogród", message_count: 2,
  last_imported_at: null };

function messageCalls() {
  return vi.mocked(axios.get).mock.calls
    .filter(([url]) => String(url).endsWith("/chat_conversations/6/messages"))
    .map(([, config]) => (config as { params: Record<string, string> }).params);
}

function renderPage(path = "/chats/6") {
  const value = { apiKey: "k", apiUrl: "http://api" } as never;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthorizationContext.Provider value={value}>
        <Routes><Route path="/chats/:id" element={<ChatConversation />} /></Routes>
      </AuthorizationContext.Provider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/chat_conversations/6/messages")) {
      return { data: { conversation: CONVERSATION, messages: [], mentions: {}, total: 0 } };
    }
    return { data: { topics: [] } };
  });
});

it("keeps chronological order by default and sends no sort", async () => {
  renderPage();
  await waitFor(() => expect(messageCalls()).toHaveLength(1));
  expect(messageCalls()[0].sort).toBeUndefined();
  expect((screen.getByLabelText("Kolejność:") as HTMLSelectElement).value).toBe("asc");
});

it("switches to newest first from page 1 and remembers the choice", async () => {
  renderPage("/chats/6?page=3");
  await waitFor(() => expect(messageCalls()).toHaveLength(1));

  fireEvent.change(screen.getByLabelText("Kolejność:"), { target: { value: "desc" } });
  await waitFor(() => expect(messageCalls()).toHaveLength(2));

  expect(messageCalls()[1]).toMatchObject({ sort: "desc", offset: "0" });
  expect(localStorage.getItem("chatMessagesSort")).toBe("desc");
  expect((screen.getByLabelText("Kolejność:") as HTMLSelectElement).value).toBe("desc");
});

it("opens newest first when the address or the remembered choice says so", async () => {
  renderPage("/chats/6?sort=desc");
  await waitFor(() => expect(messageCalls()).toHaveLength(1));
  expect(messageCalls()[0].sort).toBe("desc");

  cleanup();
  vi.mocked(axios.get).mockClear();
  localStorage.setItem("chatMessagesSort", "desc");
  renderPage("/chats/6");
  await waitFor(() => expect(messageCalls()).toHaveLength(1));
  expect(messageCalls()[0].sort).toBe("desc");
});
