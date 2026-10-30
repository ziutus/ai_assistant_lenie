import React from "react";
import axios from "axios";
import { NavLink, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination } from "../components/Pagination/pagination";
import { formatGroupDate, groupTableStyle, WhatsappGroupInfo } from "./whatsappGroups";

interface Person {
  id: number;
  phone: string | null;
  display_name: string | null;
  contact: { id: number; display_name: string | null } | null;
}
interface Member extends Person {
  is_admin: boolean;
  status: "in_contacts" | "missing" | "unverified";
  first_seen_at: string | null;
  left_at: string | null;
  can_add: boolean;
}
interface GroupEvent extends Person {
  event_type: "join" | "leave";
  detected_at: string;
  previous_synced_at: string | null;
}
interface MembersResponse {
  group: WhatsappGroupInfo;
  members: Member[];
  total: number;
  summary: { active: number; in_contacts: number; missing: number; unverified: number };
}
const statusLabels = { in_contacts: "W kontaktach", missing: "Brak w kontaktach", unverified: "Do weryfikacji" };
const controlsStyle: React.CSSProperties = { display: "flex", gap: 16, flexWrap: "wrap", margin: "20px 0" };
const contactLink = (person: Person) => person.contact && <div><NavLink to={`/contacts/${person.contact.id}`}>
  {person.contact.display_name || `Kontakt #${person.contact.id}`}
</NavLink></div>;

export default function WhatsappGroup() {
  const { id } = useParams();
  return <GroupDetails key={id} id={id!} />;
}

function GroupDetails({ id }: { id: string }) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "changes" ? "changes" : "members";
  const requestedPage = Number(searchParams.get("page") ?? 1);
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const state = ["active", "left", "all"].includes(searchParams.get("state") || "") ? searchParams.get("state")! : "active";
  const status = ["in_contacts", "missing", "unverified"].includes(searchParams.get("status") || "") ? searchParams.get("status")! : "";
  const query = searchParams.get("q") || "";
  const type = ["join", "leave"].includes(searchParams.get("type") || "") ? searchParams.get("type")! : "";
  const [data, setData] = React.useState<MembersResponse | null>(null);
  const [events, setEvents] = React.useState<{ events: GroupEvent[]; total: number } | null>(null);
  const [selected, setSelected] = React.useState<number[]>([]);
  const [confirming, setConfirming] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [result, setResult] = React.useState("");
  const [revision, setRevision] = React.useState(0);

  const updateParam = (key: string, value: string) => {
    setSelected([]); setConfirming(false);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value); else next.delete(key);
      if (key !== "page") next.delete("page");
      return next;
    }, { replace: true });
  };

  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setSelected([]); setConfirming(false);
    const timer = window.setTimeout(async () => {
      const config = { headers: { "x-api-key": apiKey }, signal: controller.signal };
      try {
        // Events do not include group metadata; request a minimal members page for the header.
        const [membersResponse, eventsResponse] = await Promise.all([
          axios.get<MembersResponse>(`${apiUrl}/whatsapp_groups/${id}/members`, {
            ...config, params: tab === "members"
              ? { state, status: status || undefined, q: query, offset: (page - 1) * 50, limit: 50 }
              : { limit: 1 },
          }),
          tab === "changes" ? axios.get<{ events: GroupEvent[]; total: number }>(`${apiUrl}/whatsapp_groups/${id}/events`, {
            ...config, params: { type: type || undefined, offset: (page - 1) * 50, limit: 50 },
          }) : Promise.resolve(null),
        ]);
        if (!controller.signal.aborted) {
          setData(membersResponse.data); setEvents(eventsResponse?.data ?? null);
          const total = eventsResponse?.data.total ?? membersResponse.data.total;
          const lastPage = Math.max(1, Math.ceil(total / 50));
          if (page > lastPage) setSearchParams((prev) => {
            const next = new URLSearchParams(prev); next.set("page", String(lastPage)); return next;
          }, { replace: true });
        }
      } catch {
        if (!controller.signal.aborted) { setError("Nie udało się pobrać danych grupy."); setData(null); setEvents(null); }
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }, 200);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [id, apiUrl, apiKey, tab, page, state, status, query, type, revision, setSearchParams]);

  const addContacts = async () => {
    if (busy || loading || !selected.length || selected.length > 50) return;
    setBusy(true); setError(""); setResult("");
    try {
      const { data: response } = await axios.post(`${apiUrl}/whatsapp_groups/${id}/members/add_contacts`,
        { member_ids: selected, fetch_photo: false }, { headers: { "x-api-key": apiKey } });
      const c = response.counts;
      setResult(`Dodano ${c.created}, powiązano ${c.linked_existing}, pominięto ${c.skipped}, błędy ${c.error}`);
      setSelected([]); setConfirming(false); setRevision((v) => v + 1);
    } catch { setError("Nie udało się dodać kontaktów. Odśwież listę przed ponowną próbą."); setSelected([]); setConfirming(false); }
    finally { setBusy(false); }
  };
  const disabled = loading || busy;

  return <section style={{ lineHeight: 1.7 }}>
    <NavLink to="/whatsapp-groups">← Grupy WhatsApp</NavLink>
    <h2>{data?.group.name || "Grupa WhatsApp"}</h2>
    {data && <>
      <p>Aktualni: {data.summary.active} · W kontaktach: {data.summary.in_contacts} · Brak w kontaktach: {data.summary.missing} · Do weryfikacji: {data.summary.unverified}</p>
      <p>Ostatni odczyt: {formatGroupDate(data.group.last_synced_at)}</p>
    </>}
    <nav aria-label="Widok grupy" style={controlsStyle}>
      <button type="button" className="button" aria-current={tab === "members" ? "page" : undefined} disabled={busy} onClick={() => updateParam("tab", "members")}>Członkowie</button>
      <button type="button" className="button" aria-current={tab === "changes" ? "page" : undefined} disabled={busy} onClick={() => updateParam("tab", "changes")}>Zmiany</button>
    </nav>
    <div style={controlsStyle}>
      {tab === "members" ? <>
        <label>Stan: <select value={state} disabled={busy} onChange={(e) => updateParam("state", e.target.value)}>
          <option value="active">Aktualni</option><option value="left">Odeszli</option><option value="all">Wszyscy</option>
        </select></label>
        <label>Status: <select value={status} disabled={busy} onChange={(e) => updateParam("status", e.target.value)}>
          <option value="">Wszyscy</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>Szukaj: <input type="search" value={query} placeholder="Nazwa lub numer" disabled={busy} onChange={(e) => updateParam("q", e.target.value)} /></label>
      </> : <label>Typ: <select value={type} disabled={busy} onChange={(e) => updateParam("type", e.target.value)}>
        <option value="">Wszystkie</option><option value="join">Dołączył(a)</option><option value="leave">Odszedł(-ęła)</option>
      </select></label>}
      <button type="button" className="button" disabled={disabled} onClick={() => setRevision((v) => v + 1)}>Odśwież</button>
    </div>
    {error && <p role="alert">{error}</p>}{result && <p role="status">{result}</p>}
    {loading && <p role="status">Ładowanie danych grupy…</p>}
    {!loading && data && tab === "members" && <>
      <p>Do weryfikacji: WhatsApp ukrył numer — nie da się bezpiecznie dopasować do kontaktu.</p>
      <div style={{ overflowX: "auto" }}><table style={groupTableStyle}>
        <thead><tr><th style={{ width: 60 }}>Wybór</th><th>Numer</th><th>Nazwa</th><th>Rola</th><th>Status</th><th>Dołączył(a) (wykryto)</th><th>Odszedł(-ęła) (wykryto)</th></tr></thead>
        <tbody>{data.members.map((m) => <tr key={m.id}>
          <td>{m.can_add && <input type="checkbox" aria-label={`Zaznacz: ${m.display_name || m.phone || m.id}`} disabled={busy}
            checked={selected.includes(m.id)} onChange={(e) => {
              setConfirming(false); setSelected((prev) => e.target.checked ? [...prev, m.id] : prev.filter((v) => v !== m.id));
            }} />}</td>
          <td>{m.phone || "Numer ukryty"}</td><td>{m.display_name || "—"}</td><td>{m.is_admin ? "Admin" : "Członek"}</td>
          <td>{statusLabels[m.status]}{contactLink(m)}</td><td>{formatGroupDate(m.first_seen_at)}</td><td>{formatGroupDate(m.left_at)}</td>
        </tr>)}</tbody>
      </table></div>
      {!data.members.length && <p>Brak osób pasujących do filtrów.</p>}
      <Pagination page={page} pageSize={50} total={data.total} isLoading={disabled} label="osób" onPageChange={(p) => updateParam("page", String(p))} />
      <p>Zaznaczanie obejmuje bieżącą stronę (do 50 osób).</p>
      <div style={controlsStyle}>
        <button type="button" className="button" disabled={disabled} onClick={() => { setSelected(data.members.filter((m) => m.can_add).map((m) => m.id)); setConfirming(false); }}>Zaznacz wszystkich brakujących</button>
        <button type="button" className="button" disabled={disabled} onClick={() => { setSelected([]); setConfirming(false); }}>Wyczyść</button>
        <button type="button" className="button" disabled={disabled || !selected.length} onClick={() => setConfirming(true)}>Dodaj zaznaczonych do kontaktów ({selected.length})</button>
      </div>
      {confirming && <div style={{ padding: 20, margin: "20px 0", border: "1px solid #ccd", borderRadius: 6 }}>
        <p>Dodać {selected.length} osób? Powstaną kontakty z grupy „WhatsApp: {data.group.name}”.</p>
        <p>Numer już w książce zostanie tylko powiązany. Zdjęcia nie są pobierane.</p>
        <div style={controlsStyle}>
          <button type="button" className="button" disabled={disabled} onClick={() => void addContacts()}>{busy ? "Dodaję…" : "Potwierdź dodanie"}</button>
          <button type="button" className="button" disabled={busy} onClick={() => setConfirming(false)}>Anuluj</button>
        </div>
      </div>}
    </>}
    {!loading && events && tab === "changes" && <>
      <p>Zmiany składu są wykrywane między odczytami. Podany przedział nie jest dokładną godziną dołączenia ani odejścia.</p>
      <div style={{ overflowX: "auto" }}><table style={{ ...groupTableStyle, minWidth: 700 }}>
        <thead><tr><th>Zmiana</th><th>Osoba</th><th>Przedział wykrycia</th></tr></thead>
        <tbody>{events.events.map((event) => <tr key={event.id}>
          <td>{event.event_type === "join" ? "Dołączył(a)" : "Odszedł(-ęła)"}</td>
          <td>{event.display_name || "—"}<div>{event.phone || "Numer ukryty"}</div>{contactLink(event)}</td>
          <td>{event.previous_synced_at
            ? `wykryto między ${formatGroupDate(event.previous_synced_at)} a ${formatGroupDate(event.detected_at)}`
            : `Wykryto ${formatGroupDate(event.detected_at)}. Brak poprzedniego odczytu.`}</td>
        </tr>)}</tbody>
      </table></div>
      {!events.events.length && <p>Brak zmian pasujących do filtra.</p>}
      <Pagination page={page} pageSize={50} total={events.total} isLoading={disabled} label="zmian" onPageChange={(p) => updateParam("page", String(p))} />
    </>}
  </section>;
}
