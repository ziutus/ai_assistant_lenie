import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";

// Status and chat selection of the live WhatsApp sync (backend/library/whatsapp_sync_routes.py).
// Nothing is archived until a chat is ticked here. Message text never appears in this panel.

interface SyncStatus {
  configured: boolean;
  connection_state: string;
  bridge_reachable: boolean;
  needs_pairing: boolean;
  bridge_checked_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  enabled_chats: number;
  media: { pending: number; unavailable: number; error: number };
  note: string;
}

interface SyncChat {
  community_group_id?: number | null;
  community_name?: string | null;
  community_jid?: string | null;
  is_community?: boolean;
  is_announce?: boolean;
  id: number;
  jid: string;
  display_name: string;
  is_group: boolean;
  enabled: boolean;
  conversation_id: number | null;
  buffered_events: number;
  last_message_at: string | null;
  last_synced_at: string | null;
}

interface Community {
  id: number;
  import_total: number;
  import_enabled: number;
}

interface ImportPreview {
  community: { id: number; name: string };
  counts: { subgroups: number; already: number; changed: number; created: number };
  enabled: boolean;
}

const STATE_LABELS: Record<string, string> = {
  connected: "połączono",
  connecting: "łączenie…",
  disconnected: "rozłączono (most próbuje wrócić)",
  needs_pairing: "wymaga sparowania",
  logged_out: "wylogowano z telefonu — wymaga ponownego sparowania",
  starting: "uruchamianie",
  unknown: "brak danych",
};

const formatDate = (value: string | null) => (value ? new Date(value).toLocaleString("pl-PL") : "—");

const WhatsappSyncPanel = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const headers = React.useMemo(() => ({ "x-api-key": `${apiKey}` }), [apiKey]);
  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState<SyncStatus | null>(null);
  const [chats, setChats] = React.useState<SyncChat[]>([]);
  const [filter, setFilter] = React.useState("");
  const [qrUrl, setQrUrl] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState("");
  const [communities, setCommunities] = React.useState<Community[]>([]);
  const [preview, setPreview] = React.useState<ImportPreview | null>(null);
  const [importBusy, setImportBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        axios.get(`${apiUrl}/whatsapp_sync/status`, { headers }),
        axios.get(`${apiUrl}/whatsapp_sync/chats`, { headers }),
      ]);
      setStatus(s.data);
      setChats(c.data.chats ?? []);
      try {
        const groups = await axios.get(`${apiUrl}/whatsapp_groups`, { headers });
        setCommunities(groups.data.groups ?? []);
      } catch {
        setCommunities([]);
        if ((c.data.chats ?? []).some((chat: SyncChat) => chat.community_group_id != null)) {
          setMessage("Nie udało się pobrać liczników społeczności. Odśwież stan, aby spróbować ponownie.");
        }
      }
    } catch (error: any) {
      setMessage(`Nie udało się pobrać stanu synchronizacji: ${error.response?.data?.message || error.message}`);
    }
  }, [apiUrl, headers]);

  React.useEffect(() => {
    load();
  }, [load]);

  React.useEffect(() => () => { if (qrUrl) URL.revokeObjectURL(qrUrl); }, [qrUrl]);

  const toggle = async (chat: SyncChat) => {
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/whatsapp_sync/chats/${chat.id}`, { enabled: !chat.enabled }, { headers });
      await load();
    } catch (error: any) {
      setMessage(`Nie udało się zmienić wyboru: ${error.response?.data?.message || error.message}`);
    }
  };

  const importCommunity = async (id: number, enabled: boolean, dryRun: boolean) => {
    setImportBusy(true);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/whatsapp_groups/${id}/import`,
        dryRun ? { enabled, dry_run: true } : { enabled }, { headers });
      if (dryRun) {
        setPreview({ ...response.data, enabled });
      } else {
        setPreview(null);
        const counts = response.data.counts;
        setMessage(`${enabled ? "Włączono" : "Wyłączono"} ${counts.changed}, utworzono ${counts.created}, już było ${counts.already}.`);
        await load();
      }
    } catch {
      setMessage("Nie udało się zmienić importu społeczności. Odśwież stan i spróbuj ponownie.");
    } finally {
      setImportBusy(false);
    }
  };

  const syncNow = async () => {
    setMessage("");
    try {
      await axios.post(`${apiUrl}/whatsapp_sync/run`, {}, { headers });
      setMessage("Synchronizacja zakolejkowana — odśwież stan za chwilę.");
    } catch (error: any) {
      setMessage(`Nie udało się zakolejkować: ${error.response?.data?.message || error.message}`);
    }
  };

  const showQr = async () => {
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/whatsapp_sync/pairing/qr.png`, { headers, responseType: "blob" });
      setQrUrl(URL.createObjectURL(response.data));
    } catch (error: any) {
      setQrUrl(null);
      setMessage(error.response?.status === 404
        ? "Most nie czeka teraz na parowanie. Jeśli konto jest wylogowane, użyj „Rozpocznij parowanie od nowa”."
        : "Nie udało się pobrać kodu QR (czy most działa?).");
    }
  };

  const resetPairing = async () => {
    setMessage("");
    try {
      await axios.post(`${apiUrl}/whatsapp_sync/pairing/reset`, {}, { headers });
      setMessage("Parowanie zrestartowane. Pokaż kod QR i zeskanuj go: WhatsApp → Połączone urządzenia.");
      await load();
    } catch (error: any) {
      setMessage(`Nie udało się zrestartować parowania: ${error.response?.data?.message || error.message}`);
    }
  };

  const shown = chats.filter((c) => !filter || c.display_name.toLowerCase().includes(filter.toLowerCase())
    || c.jid.includes(filter));
  const problem = status && (!status.bridge_reachable || status.needs_pairing || status.last_error);
  const sections = new Map<number, SyncChat[]>();
  shown.forEach((chat) => {
    if (chat.community_group_id != null) {
      const rows = sections.get(chat.community_group_id) ?? [];
      rows.push(chat);
      sections.set(chat.community_group_id, rows);
    }
  });
  const chatRows = (rows: SyncChat[]) => rows.map((c) => (
    <tr key={c.id} style={{ borderBottom: "1px solid #eee" }}>
      <td style={{ padding: "12px 6px" }}>
        <input type="checkbox" checked={c.enabled} onChange={() => toggle(c)}
          disabled={importBusy || preview !== null} aria-label={`Importuj ${c.display_name || c.jid}`} />
        <span>{c.enabled ? " Włączony" : " Wyłączony"}</span>
      </td>
      <td style={{ padding: "12px 6px" }}>{c.display_name || "(bez nazwy)"}
        {c.is_announce && <strong> — Ogłoszenia</strong>}</td>
      <td style={{ padding: "12px 6px", overflowWrap: "anywhere" }}><code>{c.jid}</code></td>
      <td style={{ padding: "12px 6px" }}>{formatDate(c.last_message_at)}</td>
      <td style={{ padding: "12px 6px" }}>
        {c.conversation_id ? <a href={`/chats/${c.conversation_id}`}>#{c.conversation_id}</a> : "—"}
      </td>
    </tr>
  ));

  return (
    <details open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      style={{ border: "1px solid #ddd", borderRadius: 6, padding: "8px 12px", marginBottom: 14 }}>
      <summary style={{ cursor: "pointer" }}>
        <strong>Synchronizacja WhatsApp</strong>
        {status && !status.configured && <span style={{ color: "#888" }}> — most nieskonfigurowany</span>}
        {status?.configured && (
          <span style={{ color: problem ? "#b36b00" : "#2a7" }}>
            {" "}— {STATE_LABELS[status.connection_state] ?? status.connection_state}
            {!status.bridge_reachable && " · most niedostępny"}
            {status.needs_pairing && " · wymagane parowanie"}
          </span>
        )}
      </summary>

      {status && (
        <div style={{ marginTop: 10 }}>
          <p style={{ color: "#667", margin: "0 0 8px" }}>
            Wiadomości z wybranych rozmów są tylko pobierane (bez wysyłania i bez oznaczania jako przeczytane).
            WhatsApp udostępnia tylko część historii i starszych załączników — to nie jest pełne archiwum.
          </p>
          <table style={{ borderCollapse: "collapse", marginBottom: 8 }}>
            <tbody>
              <tr><td style={{ padding: "2px 12px 2px 0" }}>Ostatni udany import</td><td>{formatDate(status.last_success_at)}</td></tr>
              <tr><td style={{ padding: "2px 12px 2px 0" }}>Wybrane rozmowy</td><td>{status.enabled_chats}</td></tr>
              <tr><td style={{ padding: "2px 12px 2px 0" }}>Załączniki oczekujące</td><td>{status.media.pending}</td></tr>
              <tr><td style={{ padding: "2px 12px 2px 0" }}>Załączniki niedostępne / z błędem</td>
                <td>{status.media.unavailable} / {status.media.error}</td></tr>
              {status.last_error && (
                <tr><td style={{ padding: "2px 12px 2px 0" }}>Ostatni błąd</td>
                  <td className="error">{status.last_error} ({formatDate(status.last_error_at)})</td></tr>
              )}
            </tbody>
          </table>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <button onClick={load}>Odśwież stan</button>
            <button onClick={syncNow} disabled={!status.configured}>Synchronizuj teraz</button>
            <button onClick={showQr} disabled={!status.configured}>Pokaż kod QR</button>
            <button onClick={resetPairing} disabled={!status.configured}>Rozpocznij parowanie od nowa</button>
          </div>
          {qrUrl && <img src={qrUrl} alt="Kod QR do sparowania WhatsApp" style={{ width: 240, height: 240 }} />}

          {preview && (
            <section aria-label="Potwierdzenie importu społeczności"
              style={{ padding: 20, margin: "20px 0", border: "2px solid #777", lineHeight: 1.8 }}>
              <p>{preview.enabled ? "Włączyć" : "Wyłączyć"} import {preview.counts.subgroups} podgrup
                społeczności „{preview.community.name}”
                {preview.enabled && ` (w tym ${preview.counts.created} jeszcze niewidzianych przez synchronizację)`}?</p>
              {preview.enabled && <p>Wiadomości będą pobierane od teraz oraz z historii, którą odda WhatsApp.
                Załączniki pobierają się po 2 naraz.</p>}
              <div style={{ display: "flex", gap: 20 }}>
                <button disabled={importBusy} onClick={() => importCommunity(preview.community.id, preview.enabled, false)}>
                  Potwierdź</button>
                <button disabled={importBusy} onClick={() => setPreview(null)}>Anuluj</button>
              </div>
            </section>
          )}
          {importBusy && <p role="status">Przetwarzanie importu społeczności…</p>}

          <h4 style={{ margin: "10px 0 4px" }}>Rozmowy widziane przez most</h4>
          <p style={{ color: "#667", margin: "0 0 6px" }}>
            Zaznacz rozmowy do archiwizacji. Domyślnie nic nie jest importowane. Ta sama osoba może widnieć pod
            dwoma identyfikatorami (numer i LID) — zaznacz oba wpisy.
          </p>
          <input placeholder="Filtruj po nazwie lub identyfikatorze" value={filter}
            onChange={(e) => setFilter(e.target.value)} style={{ marginBottom: 6, width: 280 }} />
          {shown.length === 0 && <p style={{ color: "#888" }}>Brak rozmów (most jeszcze niczego nie odebrał).</p>}
          {shown.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
                  <th style={{ padding: "4px 6px" }}>Importuj</th>
                  <th style={{ padding: "4px 6px" }}>Nazwa</th>
                  <th style={{ padding: "4px 6px" }}>Identyfikator</th>
                  <th style={{ padding: "4px 6px" }}>Ostatnia wiadomość</th>
                  <th style={{ padding: "4px 6px" }}>Rozmowa w Lenie</th>
                </tr>
              </thead>
              <tbody>
                {Array.from(sections, ([id, rows]) => {
                  const community = communities.find((group) => group.id === id);
                  const allRows = chats.filter((chat) => chat.community_group_id === id && !chat.is_community);
                  const total = community?.import_total ?? allRows.length;
                  const enabled = community?.import_enabled ?? allRows.filter((chat) => chat.enabled).length;
                  const allEnabled = total > 0 && enabled === total;
                  return <React.Fragment key={id}>
                    <tr><th colSpan={5} style={{ padding: "24px 6px 12px", textAlign: "left" }}>
                      <h4>{rows[0].community_name || "Społeczność"}</h4>
                      <p>{enabled} z {total} podgrup importowanych</p>
                      <button disabled={importBusy || preview !== null || !community}
                        onClick={() => importCommunity(id, !allEnabled, true)}>
                        {allEnabled ? "Wyłącz import społeczności" : "Importuj całą społeczność"}
                      </button>
                    </th></tr>
                    {chatRows([...rows].sort((a, b) => Number(!!b.is_announce) - Number(!!a.is_announce)
                      || (b.last_message_at ?? "").localeCompare(a.last_message_at ?? "")))}
                  </React.Fragment>;
                })}
                {shown.some((chat) => chat.community_group_id == null) && <>
                  <tr><th colSpan={5} style={{ padding: "24px 6px 12px", textAlign: "left" }}>Pozostałe czaty</th></tr>
                  {chatRows(shown.filter((chat) => chat.community_group_id == null))}
                </>}
              </tbody>
            </table>
          )}
        </div>
      )}
      {message && <p role="status" className={message.startsWith("Nie udało") ? "error" : undefined}>{message}</p>}
    </details>
  );
};

export default WhatsappSyncPanel;
