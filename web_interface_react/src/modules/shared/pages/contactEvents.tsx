import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination } from "../components/Pagination/pagination";
import type { ContactGroupEvent } from "./contactGroupDetail";
import type { ContactGroup } from "./contactGroups";

type Participant = ContactGroupEvent["participants"][number];
interface EventForm {
  title: string;
  event_date: string;
  summary: string;
  group_id: number | null;
  participants: Participant[];
}
const emptyForm: EventForm = { title: "", event_date: "", summary: "", group_id: null, participants: [] };
const rowStyle: React.CSSProperties = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" };
const chipStyle: React.CSSProperties = { display: "inline-block", padding: "2px 8px", borderRadius: 12, background: "#eef2ff" };
const pageSize = 50;

const ContactEvents = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [events, setEvents] = React.useState<ContactGroupEvent[]>([]);
  const [groups, setGroups] = React.useState<ContactGroup[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [form, setForm] = React.useState<EventForm>(emptyForm);
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<Participant[]>([]);
  const [targetId, setTargetId] = React.useState<number | null>(null);
  const [searching, setSearching] = React.useState(false);
  const searchVersion = React.useRef(0);
  const [page, setPage] = React.useState(1);
  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };
  const report = (text: string, error = false) => { setMessage(text); setIsError(error); };
  const resetPicker = () => {
    searchVersion.current += 1;
    setQuery(""); setResults([]); setTargetId(null); setSearching(false);
  };
  const resetForm = () => { setEditId(null); setForm(emptyForm); resetPicker(); };

  React.useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setEvents([]); setGroups([]); setPage(1); resetForm(); report("");
    Promise.all([
      axios.get(`${apiUrl}/contact_events`, { headers }),
      axios.get(`${apiUrl}/contact_groups`, { headers }),
    ]).then(([eventResponse, groupResponse]) => {
      if (!cancelled) {
        setEvents(eventResponse.data.events);
        setGroups(groupResponse.data.contact_groups);
      }
    }).catch(error => {
      if (!cancelled) report(`Nie udało się pobrać wydarzeń: ${error.response?.data?.message || error.message}`, true);
    }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; searchVersion.current += 1; };
  }, [apiUrl, apiKey]);

  const searchParticipants = async () => {
    const version = ++searchVersion.current;
    setSearching(true); setResults([]); setTargetId(null);
    try {
      const response = await axios.get(`${apiUrl}/contacts`, {
        params: query.trim() ? { q: query.trim() } : {}, headers,
      });
      if (version === searchVersion.current) setResults(response.data.contacts ?? []);
    } catch (error: any) {
      if (version === searchVersion.current) report(`Nie udało się wyszukać kontaktów: ${error.response?.data?.message || error.message}`, true);
    } finally { if (version === searchVersion.current) setSearching(false); }
  };

  const save = async () => {
    if (!form.title.trim() || !form.event_date) {
      report("Tytuł i data są wymagane.", true); return;
    }
    if (form.group_id === null && !form.participants.length) {
      report("Wydarzenie musi być powiązane z grupą lub co najmniej jednym kontaktem.", true); return;
    }
    setBusy(true); report("");
    const payload = {
      title: form.title, event_date: form.event_date, summary: form.summary,
      group_id: form.group_id, participant_contact_ids: form.participants.map(contact => contact.id),
    };
    try {
      const response = editId === null
        ? await axios.post(`${apiUrl}/contact_events`, payload, { headers })
        : await axios.patch(`${apiUrl}/contact_group_events/${editId}`, payload, { headers });
      const saved: ContactGroupEvent = response.data.event;
      setEvents(current => [...current.filter(event => event.id !== saved.id), saved]
        .sort((a, b) => b.event_date.localeCompare(a.event_date) || b.id - a.id));
      resetForm(); setPage(1); report("Zapisano wydarzenie.");
    } catch (error: any) {
      report(`Nie udało się zapisać: ${error.response?.data?.message || error.message}`, true);
    } finally { setBusy(false); }
  };

  const remove = async (event: ContactGroupEvent) => {
    if (!window.confirm(`Usunąć wydarzenie „${event.title}”?`)) return;
    setBusy(true); report("");
    try {
      await axios.delete(`${apiUrl}/contact_group_events/${event.id}`, { headers });
      setEvents(current => current.filter(row => row.id !== event.id));
      if (editId === event.id) resetForm();
      setPage(current => Math.min(current, Math.max(1, Math.ceil((events.length - 1) / pageSize))));
      report("Usunięto wydarzenie.");
    } catch (error: any) {
      report(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`, true);
    } finally { setBusy(false); }
  };
  const availableResults = results.filter(result => !form.participants.some(contact => contact.id === result.id));

  return <div>
    <h2>Wydarzenia</h2>
    {message && <p role={isError ? "alert" : "status"} style={{ color: isError ? "#b91c1c" : "#166534" }}>{message}</p>}
    {isLoading && <p>Ładowanie…</p>}
    <form onSubmit={event => { event.preventDefault(); void save(); }}>
      <fieldset disabled={busy || isLoading} style={{ border: "1px solid #d5dde8", borderRadius: 6, padding: 12 }}>
        <legend>{editId === null ? "Dodaj wydarzenie" : "Edytuj wydarzenie"}</legend>
        <div style={rowStyle}>
          <label>Tytuł <input required maxLength={255} value={form.title}
            onChange={event => setForm({ ...form, title: event.target.value })} /></label>
          <label>Data <input required type="date" value={form.event_date}
            onChange={event => setForm({ ...form, event_date: event.target.value })} /></label>
          <label>Grupa (opcjonalnie) <select value={form.group_id ?? ""}
            onChange={event => setForm({ ...form, group_id: event.target.value ? Number(event.target.value) : null })}>
            <option value="">Bez grupy</option>
            {groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}
          </select></label>
          <label>Opis <textarea value={form.summary}
            onChange={event => setForm({ ...form, summary: event.target.value })} /></label>
        </div>
        <p>Wybierz grupę lub dodaj uczestników. Możesz wskazać oba powiązania.</p>
        <div style={{ ...rowStyle, marginBottom: 8 }}>
          <label>Uczestnicy <input value={query} placeholder="Szukaj kontaktu..."
            onChange={event => setQuery(event.target.value)} onKeyDown={event => {
              if (event.key === "Enter") { event.preventDefault(); void searchParticipants(); }
            }} /></label>
          <button className="button" type="button" disabled={searching} onClick={searchParticipants}>
            {searching ? "Szukanie…" : "Szukaj"}
          </button>
          {availableResults.length > 0 && <>
            <select aria-label="Wybierz uczestnika" value={targetId ?? ""}
              onChange={event => setTargetId(event.target.value ? Number(event.target.value) : null)}>
              <option value="">Wybierz kontakt...</option>
              {availableResults.map(contact => <option key={contact.id} value={contact.id}>{contact.display_name}</option>)}
            </select>
            <button className="button" type="button" disabled={targetId === null} onClick={() => {
              const contact = availableResults.find(result => result.id === targetId);
              if (contact) setForm(current => ({ ...current, participants: [...current.participants, contact] }));
              setTargetId(null);
            }}>Dodaj uczestnika</button>
          </>}
        </div>
        <div style={{ ...rowStyle, marginBottom: 8 }}>
          {form.participants.map(contact => <span key={contact.id} style={chipStyle}>
            {contact.display_name}{" "}
            <button type="button" aria-label={`Usuń uczestnika ${contact.display_name}`} onClick={() => {
              setForm(current => ({ ...current, participants: current.participants.filter(row => row.id !== contact.id) }));
            }}>×</button>
          </span>)}
        </div>
        <button className="button" type="submit">{editId === null ? "Dodaj wydarzenie" : "Zapisz"}</button>{" "}
        {editId !== null && <button className="button" type="button" onClick={resetForm}>Anuluj</button>}
      </fieldset>
    </form>
    <ul style={{ listStyle: "none", padding: 0 }}>
      {events.slice((page - 1) * pageSize, page * pageSize).map(event => <li key={event.id}
        style={{ padding: "12px 0", borderBottom: "1px solid #eee" }}>
        <div style={rowStyle}>
          <time dateTime={event.event_date}>{event.event_date}</time><strong>{event.title}</strong>
          <button className="button" type="button" disabled={busy} onClick={() => {
            setEditId(event.id);
            setForm({ title: event.title, event_date: event.event_date, summary: event.summary ?? "",
              group_id: event.group_id, participants: event.participants });
            resetPicker(); report("");
          }}>Edytuj</button>
          <button className="button" type="button" disabled={busy} onClick={() => remove(event)}>Usuń</button>
        </div>
        {event.summary && <p style={{ whiteSpace: "pre-wrap" }}>{event.summary}</p>}
        <div style={{ ...rowStyle, marginTop: 6 }}>
          {event.group_id !== null && <NavLink style={chipStyle} to={`/contact_groups/${event.group_id}`}>{event.group_name}</NavLink>}
          {event.participants.map(contact => <NavLink key={contact.id} style={chipStyle} to={`/contacts/${contact.id}`}>
            {contact.display_name}
          </NavLink>)}
        </div>
      </li>)}
    </ul>
    {!isLoading && !events.length && <p style={{ color: "#667" }}>Brak wydarzeń — dodaj pierwsze powyżej.</p>}
    <Pagination page={page} pageSize={pageSize} total={events.length} isLoading={busy || isLoading}
      label="wydarzeń" onPageChange={setPage} />
  </div>;
};

export default ContactEvents;
