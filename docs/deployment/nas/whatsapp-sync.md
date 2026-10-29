# WhatsApp live sync (NAS)

Read-only, continuous archive of **selected** WhatsApp chats into Lenie
(`/chats`) and their attachments into MinIO. Design and trade-offs:
[ADR-031](../../adr/adr-031-whatsapp-live-sync-bridge.md). Nothing is ever sent
to WhatsApp, no message is marked as read, no LLM runs over the messages.

```
WhatsApp ── linked device ──> lenie-whatsapp-bridge (Go, journal in a volume)
                                   ^ pull, then ack
                lenie-worker job `whatsapp_sync` (every 5 min) ──> PostgreSQL + MinIO ──> /chats
```

**WhatsApp provides only part of the history and part of older media.** The archive is
best-effort: do not treat it as complete.

## 1. One-time setup

1. Pick a secret of at least 16 characters (`openssl rand -hex 24`).
2. NAS env file `/share/Container/lenie-env/.env`: `WA_BRIDGE_TOKEN=<secret>`.
3. Vault (same secret, backend side): `WHATSAPP_BRIDGE_TOKEN=<secret>` and
   `WHATSAPP_BRIDGE_URL=http://lenie-whatsapp-bridge:8095`.
   Optional keys: `WHATSAPP_SYNC_TIMEZONE` (default `Europe/Warsaw`; TXT exports store naive local
   time and synced messages use the same convention), `WHATSAPP_OWN_SENDER_NAME` (default `Ja`),
   `WHATSAPP_MEDIA_MAX_BYTES` (default 50 MiB).
4. Deploy from the home LAN (see AGENTS.md): `bash ./infra/docker/nas-deploy.sh backend whatsapp-bridge`
   (`backend` also recreates the worker and runs the Alembic migration `e4a7c1d9b358`).
   Until Vault has the URL/token the `whatsapp_sync` job is a no-op.

## 2. Pairing (QR)

The bridge port is published on the NAS loopback only. Either use the Lenie UI or a tunnel:

- **UI:** `/chats` → *Synchronizacja WhatsApp* → *Pokaż kod QR* (proxied by the backend, needs a user key).
- **Tunnel:** `ssh -L 8095:127.0.0.1:8095 admin@192.168.200.7`, then
  `curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8095/pairing/qr.png -o qr.png`.

On the phone: WhatsApp → *Settings → Linked devices → Link a device*, scan the code. The code
refreshes every ~20 s; reload it if it expires. The device appears as "Lenie archive"
(`WA_BRIDGE_DEVICE_NAME`). QR codes and session keys are never logged.

**Re-pairing** (status `logged_out` / "wymaga ponownego sparowania", e.g. the device was removed on the
phone or WhatsApp logged it out): *Rozpocznij parowanie od nowa*, then scan again. Existing Lenie data
is untouched; the cursors survive, and re-delivered history cannot duplicate (unique WhatsApp ids).

## 3. Choosing chats

Right after pairing the bridge lists every chat it sees, but **nothing is imported by default**.
In *Synchronizacja WhatsApp* tick the chats to archive (identified by stable JID, e.g.
`48...@s.whatsapp.net`, `120363...@g.us`). A person may show up twice (phone-number JID and `@lid`)
— tick both. A new conversation `whatsapp:<jid>` is created per chat; to append to an existing
imported conversation, link it with
`PATCH /whatsapp_sync/chats/<id> {"conversation_id": <conversation id>, "enabled": true}` first.

History the phone sent at pairing for chats you tick *later* is still available for 7 days
(`WA_BRIDGE_UNSELECTED_RETENTION_HOURS`); after that only new messages arrive. If you want the full
available history, tick the chats within a week of pairing.

## 4. What is stored

Text, sender (push name, JID/LID, phone when known), time, direction (`is_from_me`), WhatsApp ids,
edits (`edited_at`, newest edit wins), deletions (`message_type='deleted'`, text and attachment removed
from the record and from MinIO), captions, contact cards (name only). Reactions, polls and system events
are not stored in v1. Contacts are matched only by phone number against the existing contact book;
no contact is created.

Attachments are fetched separately from the message, 20 per cycle, 2 in parallel, ≤ 50 MiB, to
`chat_media/whatsapp/<conversation id>/<hash of chat+message id>.<ext>` (the sender's file name is
never used in keys). Status per message: `pending` (retrying with 1 min → 6 h backoff, 8 attempts),
`downloaded`, `unavailable` (gone from WhatsApp or too large), `error` (gave up).

Known limits: edits or deletions that happened while the bridge was offline are not replayed;
a TXT/ZIP-imported message is merged with its synced twin only when text+minute match exactly one
row (otherwise both stay); attachments of TXT imports are never matched.

## 5. Backup and restore

State lives in the Docker volume `lenie-whatsapp-data` (`session.db` = device keys,
`journal.db`). Losing `session.db` only means re-pairing; losing the journal loses at most
messages not yet acknowledged.

```
docker run --rm -v lenie-whatsapp-data:/data -v /share/Backup:/backup alpine \
  tar czf /backup/lenie-whatsapp-$(date +%F).tgz -C /data .
```

The archive contains the device keys: store it like a password, never in git. Restore by extracting
into an empty volume before starting the container.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| Panel: "most niedostępny" | `docker logs lenie-whatsapp-bridge`; token mismatch → `bridge rejected the token` in *Ostatni błąd* |
| `needs_pairing` / `logged_out` | pair again (section 2) |
| "session replaced by another client" | the same session files are used by two containers — keep exactly one bridge |
| "WhatsApp rejected the client version" | rebuild the bridge image with an updated whatsmeow: `go get go.mau.fi/whatsmeow@latest` in `whatsapp_bridge/` |
| Messages missing | chat not ticked; chat shown under its other JID/LID; WhatsApp did not send that history |
| Attachments `pending` for long | bridge disconnected (they are only fetched while connected) or backoff; `unavailable` is final |
| Reset everything | stop the container, `docker volume rm lenie-whatsapp-data`, start, pair; Lenie data stays |

Logs never contain message text, QR codes or keys. Message content is rendered as plain text in the UI.
