import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { Pagination } from "../../components/Pagination/pagination";

interface Sender {
  key: string;
  name: string;
  nickname: string | null;
  phone: string | null;
  message_count: number;
  last_at: string | null;
  contact: { id: number; display_name: string | null } | null;
  status: "missing" | "in_contacts";
  sample_message_id: number;
  can_add: boolean;
}
interface SenderList {
  senders: Sender[];
  total: number;
  summary: { senders: number; in_contacts: number; missing: number };
}

export default function ChatSendersPanel({ id, channel, apiUrl, apiKey, onSender, onAdded }: {
  id: string; channel: string; apiUrl: string; apiKey: string;
  onSender: (name: string) => void; onAdded: () => void;
}) {
  const [open, setOpen] = React.useState(() => {
    try { return localStorage.getItem("chatSendersOpen") === "true"; } catch { return false; }
  });
  const [status, setStatus] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedPage = Number(searchParams.get("senders_page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const setPage = (value: number) => setSearchParams((prev) => {
    const next = new URLSearchParams(prev);
    if (value === 1) next.delete("senders_page"); else next.set("senders_page", String(value));
    return next;
  }, { replace: true });
  const [data, setData] = React.useState<SenderList | null>(null);
  const [selected, setSelected] = React.useState<number[]>([]);
  const [confirm, setConfirm] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [result, setResult] = React.useState("");
  const [revision, setRevision] = React.useState(0);

  React.useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true); setError(""); setSelected([]); setConfirm(false);
    const timer = window.setTimeout(() => {
      axios.get<SenderList>(`${apiUrl}/chat_conversations/${id}/senders`, {
        headers: { "x-api-key": apiKey }, signal: controller.signal,
        params: { status: status || undefined, q: query, offset: (page - 1) * 50, limit: 50 },
      }).then(({ data: next }) => setData(next)).catch(() => {
        if (!controller.signal.aborted) { setError("Nie udało się pobrać uczestników."); setData(null); }
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 200);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [id, apiUrl, apiKey, open, status, query, page, revision]);

  const add = async () => {
    setBusy(true); setError(""); setResult("");
    try {
      const response = await axios.post(`${apiUrl}/chat_conversations/${id}/senders/add_contacts`,
        { message_ids: selected, fetch_photo: false }, { headers: { "x-api-key": apiKey } });
      const c = response.data.counts;
      setResult(`Dodano ${c.created}, powiązano ${c.linked_existing}, pominięto ${c.skipped}, błędy ${c.error}`);
      setSelected([]); setConfirm(false); setRevision((v) => v + 1); onAdded();
    } catch { setError("Nie udało się dodać kontaktów. Odśwież listę przed ponowną próbą."); }
    finally { setBusy(false); }
  };
  const disabled = loading || busy;
  return (
    <section style={{ border: "1px solid #ccd", borderRadius: 6, padding: 16, marginBottom: 20, lineHeight: 1.7 }}>
      <button type="button" className="button" aria-expanded={open} aria-controls="chat-senders" disabled={busy}
        onClick={() => {
          setOpen(!open);
          try { localStorage.setItem("chatSendersOpen", String(!open)); } catch { /* Storage may be unavailable. */ }
        }}>Uczestnicy {open ? "▴" : "▾"}</button>
      {open && <div id="chat-senders">
        {data && <p>Piszą w tym kanale: {data.summary.senders} osób · W kontaktach: {data.summary.in_contacts} · Brak: {data.summary.missing}</p>}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "16px 0" }}>
          <label>Status: <select value={status} disabled={busy} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">Wszyscy</option><option value="missing">Brak w kontaktach</option>
            <option value="in_contacts">W kontaktach</option>
          </select></label>
          <label>Szukaj: <input type="search" value={query} disabled={busy} placeholder="Nazwa lub numer"
            onChange={(e) => { setQuery(e.target.value); setPage(1); }} /></label>
          <button type="button" className="button" disabled={disabled} onClick={() => setRevision((v) => v + 1)}>Odśwież</button>
        </div>
        {error && <p role="alert">{error}</p>}
        {result && <p role="status">{result}</p>}
        {loading && <p role="status">Ładowanie uczestników…</p>}
        {!loading && data && <>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", tableLayout: "fixed", minWidth: 850, borderSpacing: "12px 16px", textAlign: "left" }}>
              <thead><tr><th style={{ width: 40 }}>Wybór</th><th>Nazwa</th><th>Numer</th><th>Wiadomości</th><th>Ostatnia aktywność</th><th>Status</th></tr></thead>
              <tbody>{data.senders.map((s) => <tr key={s.key}>
                <td>{s.can_add && <input type="checkbox" aria-label={`Zaznacz: ${s.name || s.key}`} disabled={busy}
                  checked={selected.includes(s.sample_message_id)} onChange={(e) => {
                    setConfirm(false);
                    setSelected((prev) => e.target.checked ? [...prev, s.sample_message_id] : prev.filter((v) => v !== s.sample_message_id));
                  }} />}</td>
                <td style={{ overflowWrap: "anywhere" }}><button type="button" className="button" onClick={() => onSender(s.name)}>{s.name || s.key}</button>
                  {s.nickname && s.nickname !== s.name && <div>{s.nickname}</div>}</td>
                <td style={{ overflowWrap: "anywhere" }}>{s.phone || "—"}</td><td>{s.message_count}</td>
                <td>{s.last_at ? new Date(s.last_at).toLocaleDateString("pl-PL") : "—"}</td>
                <td>{s.status === "in_contacts" ? "W kontaktach" : "Brak w kontaktach"}
                  {s.contact && <div><NavLink to={`/contacts/${s.contact.id}`}>{s.contact.display_name || `Kontakt #${s.contact.id}`}</NavLink></div>}</td>
              </tr>)}</tbody>
            </table>
          </div>
          {!data.senders.length && <p>Brak uczestników pasujących do filtra.</p>}
          <Pagination page={page} pageSize={50} total={data.total} isLoading={disabled} label="osób" onPageChange={setPage} />
          <p>Zaznaczanie obejmuje bieżącą stronę (do 50 osób).</p>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <button type="button" className="button" disabled={disabled} onClick={() => {
              setSelected(data.senders.filter((s) => s.can_add).map((s) => s.sample_message_id)); setConfirm(false);
            }}>Zaznacz wszystkich brakujących</button>
            <button type="button" className="button" disabled={disabled} onClick={() => { setSelected([]); setConfirm(false); }}>Wyczyść</button>
            <button type="button" className="button" disabled={disabled || !selected.length} onClick={() => setConfirm(true)}>
              Dodaj zaznaczonych do kontaktów ({selected.length})</button>
          </div>
          {confirm && <div style={{ padding: 16, marginTop: 16, background: "#eef6ff" }}>
            <p>Dodać {selected.length} osób? Powstaną kontakty z grupy „WhatsApp: {channel}”.</p>
            <p>Numer już istniejący w książce zostanie tylko powiązany. Zdjęcia nie są pobierane.</p>
            <button type="button" className="button" disabled={disabled} onClick={() => void add()}>{busy ? "Dodaję…" : "Potwierdź dodanie"}</button>{" "}
            <button type="button" className="button" disabled={busy} onClick={() => setConfirm(false)}>Anuluj</button>
          </div>}
        </>}
      </div>}
    </section>
  );
}
