# ADR-031: WhatsApp live sync through our own receive-only whatsmeow bridge

- Status: accepted (2026-10-29)
- Context: replaces manual TXT/ZIP exports (`backend/imports/whatsapp_chat_import.py`) with continuous, read-only sync of selected chats into `chat_conversations` / `chat_messages` and attachments into MinIO.

## Decision

A small Go service, `whatsapp_bridge/`, built **directly on [whatsmeow](https://github.com/tulir/whatsmeow)**
(MPL-2.0, actively maintained — last push 2026-10-28), plus a Python adapter in the backend
(`library/whatsapp_sync_service.py`, worker job `whatsapp_sync`). No MCP in the import path.

The bridge pairs as an additional device (QR), journals decoded events into a durable SQLite file
and serves them through an authenticated REST API on the private Docker network. The adapter pulls,
stores, then acknowledges. The bridge contains no code that sends, replies, or marks messages read.

## Candidates reviewed

| Candidate | Licence | State | Verdict |
|---|---|---|---|
| `lharries/whatsapp-mcp` | MIT | ~6.7k stars, last push 2025-07 | Rejected as a base |
| `quauhtlimtz/whatsapp-mcp` | MIT | fork, 1 star, 2026-10 | Rejected as a base |
| whatsmeow | MPL-2.0 | very active | **Chosen** (library) |

Verified in `lharries/whatsapp-mcp` `whatsapp-bridge/main.go` (the quauhtlimtz fork keeps the same bridge and adds interactive replies):

- the bridge REST API exposes only `/api/send` and `/api/download`: no listing of chats, no
  events feed, no allowlist — the data path to Python is "read the bridge's SQLite file", i.e. the
  MCP server and the import would be coupled through someone else's schema;
- sending is built in and on by default, which our requirement forbids (it would have to be removed or fenced off);
- it stores every chat's text in SQLite without an allowlist, handles `events.Message` and history
  but has no handling of edits or revocations and takes only `Info.Sender.User` as the sender (a
  LID would be stored as if it were a phone number), and downloads media only on demand through its
  MCP tool;
- the forks pin a vendored, patched copy of whatsmeow, which is a maintenance liability.

Owning ~600 lines of Go on top of the upstream library is smaller than auditing and patching those
bridges, and gives us exactly the semantics we need.

## Consequences

- Journal + acknowledgement: the bridge keeps events until the adapter commits them
  (`cursor_seq` per chat in the same transaction as the messages), so a crash on either side
  cannot lose or duplicate a message. A journal `epoch` detects a recreated volume.
- Messages from chats that are **not selected** are buffered only briefly in the bridge volume
  (default 7 days, `WA_BRIDGE_UNSELECTED_RETENTION_HOURS`) so history that arrives at pairing time
  is not lost when the owner picks chats afterwards; they never reach the Lenie database.
- Identity: `(chat JID, message id)` is unique in `chat_messages`; both JID and LID of a sender are
  stored, a contact is resolved only through a phone number (a bare LID is never guessed), and no
  contact is created for group members.
- Coexistence with TXT/ZIP imports: a synced message adopts an old import row only when exactly one
  row has the same text in the same minute and nothing else competes for it. Everything else stays
  separate and may appear twice — a documented limitation, preferred over merging different messages.
- Limits we cannot remove: WhatsApp sends only part of the history and part of old media at pairing;
  edits/revocations that happened while the bridge was offline are not replayed by WhatsApp;
  reactions and polls are ignored in v1; whatsmeow is an unofficial client, so a protocol change or
  account action by WhatsApp can interrupt sync until the image is updated.
