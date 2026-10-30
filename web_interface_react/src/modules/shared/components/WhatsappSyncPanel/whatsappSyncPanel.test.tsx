import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthorizationContext } from "../../context/authorizationContext";
import WhatsappSyncPanel from "./whatsappSyncPanel";

vi.mock("axios");
afterEach(cleanup);

const STATUS = { status: "success", configured: true, connection_state: "connected", bridge_reachable: true,
  needs_pairing: false, last_success_at: null, last_error: null, last_error_at: null, enabled_chats: 0,
  media: { pending: 0, unavailable: 0, error: 0 } };

const chat = (id: number, name: string, communityId: number, communityName: string, extra = {}) => ({
  id, jid: `${id}@g.us`, display_name: name, is_group: true, enabled: false, conversation_id: null,
  buffered_events: 0, last_message_at: null, last_synced_at: null, community_group_id: communityId,
  community_jid: `c${communityId}@g.us`, community_name: communityName, is_community: false, is_announce: false,
  ...extra,
});

const CHATS = { chats: [
  chat(1, "Dom - ogłoszenia", 10, "Dom", { is_announce: true }), chat(2, "Dom - ogród", 10, "Dom"),
  chat(3, "Inna - sub", 20, "Inna"), chat(4, "Zwykła", 0, "", { community_group_id: null, community_name: null }),
] };
const GROUPS = { groups: [
  { id: 10, jid: "c10@g.us", name: "Dom", is_community: true, import_total: 2, import_enabled: 0 },
  { id: 20, jid: "c20@g.us", name: "Inna", is_community: true, import_total: 1, import_enabled: 0 },
] };

function renderPanel() {
  const value = { apiKey: "k", apiUrl: "http://api" } as never;
  return render(<AuthorizationContext.Provider value={value}><WhatsappSyncPanel /></AuthorizationContext.Provider>);
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/whatsapp_sync/status")) return { data: STATUS };
    if (url.endsWith("/whatsapp_sync/chats")) return { data: CHATS };
    if (url.endsWith("/whatsapp_groups")) return { data: GROUPS };
    throw new Error(`unexpected GET ${url}`);
  });
});

const startButtons = () => screen.getAllByRole("button", { name: "Importuj całą społeczność" });

it("opens the confirmation under the clicked community and keeps everything else usable", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { dry_run: true, community: { id: 10, name: "Dom" },
    counts: { subgroups: 2, already: 0, changed: 2, created: 0 } } });
  renderPanel();
  await waitFor(() => expect(startButtons()).toHaveLength(2));

  fireEvent.click(startButtons()[0]);
  const confirmation = await screen.findByLabelText("Potwierdzenie importu społeczności");

  // It sits between the clicked community header and the next one, not at the top of the panel.
  const dom = screen.getByRole("heading", { name: "Dom" });
  const inna = screen.getByRole("heading", { name: "Inna" });
  expect(dom.compareDocumentPosition(confirmation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(confirmation.compareDocumentPosition(inna) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  // A preview writes nothing, so it must not freeze the other communities or the per-chat checkboxes.
  startButtons().forEach((button) => expect((button as HTMLButtonElement).disabled).toBe(false));
  const boxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
  expect(boxes.length).toBeGreaterThan(0);
  boxes.forEach((box) => expect(box.disabled).toBe(false));
});

it("reports the result under the clicked community after confirming", async () => {
  vi.mocked(axios.post)
    .mockResolvedValueOnce({ data: { dry_run: true, community: { id: 10, name: "Dom" },
      counts: { subgroups: 2, already: 0, changed: 2, created: 0 } } })
    .mockResolvedValueOnce({ data: { dry_run: false, community: { id: 10, name: "Dom" },
      counts: { subgroups: 2, already: 0, changed: 2, created: 0 } } });
  renderPanel();
  await waitFor(() => expect(startButtons()).toHaveLength(2));

  fireEvent.click(startButtons()[0]);
  fireEvent.click(await screen.findByRole("button", { name: "Potwierdź" }));

  const result = await screen.findByText("Włączono 2, utworzono 0, już było 0.");
  const dom = screen.getByRole("heading", { name: "Dom" });
  const inna = screen.getByRole("heading", { name: "Inna" });
  expect(dom.compareDocumentPosition(result) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(result.compareDocumentPosition(inna) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByLabelText("Potwierdzenie importu społeczności")).toBeNull();
  expect(axios.post).toHaveBeenLastCalledWith("http://api/whatsapp_groups/10/import", { enabled: true },
    { headers: { "x-api-key": "k" } });
});

it("shows a failed import under the clicked community", async () => {
  vi.mocked(axios.post).mockRejectedValue(new Error("boom"));
  renderPanel();
  await waitFor(() => expect(startButtons()).toHaveLength(2));
  fireEvent.click(startButtons()[1]);
  const error = await screen.findByText(/Nie udało się zmienić importu społeczności/);
  const inna = screen.getByRole("heading", { name: "Inna" });
  expect(inna.compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
