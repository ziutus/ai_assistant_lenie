import React from "react";
import axios from "axios";
import { NavLink, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import type { ContactGroup } from "./contactGroups";

export interface ContactGroupEvent {
  id: number;
  group_id: number;
  title: string;
  event_date: string;
  summary: string | null;
  source_document_id: number | null;
  source_document_title: string | null;
  created_at: string;
  updated_at: string;
}

interface GroupDetail extends ContactGroup { events: ContactGroupEvent[] }
const emptyForm = { title: "", event_date: "", summary: "" };

const ContactGroupDetail = () => {
  const { id } = useParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [group, setGroup] = React.useState<GroupDetail | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [busyId, setBusyId] = React.useState<number | null>(null);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [addForm, setAddForm] = React.useState(emptyForm);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [editForm, setEditForm] = React.useState(emptyForm);
  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };
  const report = (text: string, error = false) => { setIsError(error); setMessage(text); };

  React.useEffect(() => {
    let cancelled = false;
    setGroup(null);
    setIsLoading(true);
    setEditId(null);
    setAddForm(emptyForm);
    report("");
    axios.get(`${apiUrl}/contact_groups/${id}`, { headers }).then(response => {
      if (!cancelled) setGroup(response.data.contact_group);
    }).catch(error => {
      if (!cancelled) report(`Nie udało się pobrać grupy: ${error.response?.data?.message || error.message}`, true);
    }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, apiKey, id]);

  const save = async (eventId: number | null) => {
    const form = eventId === null ? addForm : editForm;
    if (!form.title.trim() || !form.event_date) {
      report("Tytuł i data są wymagane.", true);
      return;
    }
    setBusyId(eventId ?? 0);
    report("");
    try {
      const response = eventId === null
        ? await axios.post(`${apiUrl}/contact_groups/${id}/events`, form, { headers })
        : await axios.patch(`${apiUrl}/contact_group_events/${eventId}`, form, { headers });
      const saved: ContactGroupEvent = response.data.event;
      setGroup(current => current && ({ ...current, events: [
        ...current.events.filter(event => event.id !== saved.id), saved,
      ].sort((a, b) => b.event_date.localeCompare(a.event_date) || b.id - a.id) }));
      if (eventId === null) setAddForm(emptyForm);
      else setEditId(null);
      report("Zapisano wydarzenie.");
    } catch (error: any) {
      report(`Nie udało się zapisać: ${error.response?.data?.message || error.message}`, true);
    } finally { setBusyId(null); }
  };

  const remove = async (event: ContactGroupEvent) => {
    if (!window.confirm(`Usunąć wydarzenie „${event.title}”?`)) return;
    setBusyId(event.id);
    report("");
    try {
      await axios.delete(`${apiUrl}/contact_group_events/${event.id}`, { headers });
      setGroup(current => current && ({ ...current, events: current.events.filter(row => row.id !== event.id) }));
      report("Usunięto wydarzenie.");
    } catch (error: any) {
      report(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`, true);
    } finally { setBusyId(null); }
  };

  const fields = (form: typeof emptyForm, setForm: (value: typeof emptyForm) => void) => (
    <>
      <label>Tytuł <input required maxLength={255} value={form.title}
        onChange={e => setForm({ ...form, title: e.target.value })} /></label>
      <label>Data <input required type="date" value={form.event_date}
        onChange={e => setForm({ ...form, event_date: e.target.value })} /></label>
      <label>Opis <textarea value={form.summary}
        onChange={e => setForm({ ...form, summary: e.target.value })} /></label>
    </>
  );
  const formStyle: React.CSSProperties = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" };

  return (
    <div>
      <NavLink to="/contact-groups">← Grupy kontaktów</NavLink>
      {isLoading && <p>Ładowanie…</p>}
      {message && <p role={isError ? "alert" : "status"} style={{ color: isError ? "#b91c1c" : "#166534" }}>{message}</p>}
      {group && <>
        <h2>{group.name}</h2>
        {group.description && <p>{group.description}</p>}
        <p>Liczba członków: {group.count}</p>
        <NavLink to={`/contacts?group_filter=1&group_ids=${group.id}`}>Zobacz członków</NavLink>
        <h3>Wydarzenia</h3>
        <form style={formStyle} onSubmit={e => { e.preventDefault(); void save(null); }}>
          {fields(addForm, setAddForm)}
          <button className="button" disabled={busyId !== null} type="submit">Dodaj wydarzenie</button>
        </form>
        <ul style={{ listStyle: "none", padding: 0 }}>
          {group.events.map(event => <li key={event.id}
            style={{ padding: "12px 0", borderBottom: "1px solid #eee", opacity: busyId === event.id ? 0.5 : 1 }}>
            {editId === event.id ? (
              <form style={formStyle} onSubmit={e => { e.preventDefault(); void save(event.id); }}>
                {fields(editForm, setEditForm)}
                <button className="button" disabled={busyId !== null} type="submit">Zapisz</button>
                <button className="button" disabled={busyId !== null} type="button" onClick={() => setEditId(null)}>Anuluj</button>
              </form>
            ) : <>
              <div style={formStyle}>
                <time dateTime={event.event_date}>{event.event_date}</time><strong>{event.title}</strong>
                <button className="button" disabled={busyId !== null} type="button" onClick={() => {
                  setEditId(event.id);
                  setEditForm({ title: event.title, event_date: event.event_date, summary: event.summary ?? "" });
                }}>Edytuj</button>
                <button className="button" disabled={busyId !== null} type="button" onClick={() => remove(event)}>Usuń</button>
              </div>
              {event.summary && <p style={{ whiteSpace: "pre-wrap" }}>{event.summary}</p>}
              {event.source_document_id !== null && <NavLink to={`/read/${event.source_document_id}`}>
                {event.source_document_title || `Dokument #${event.source_document_id}`}
              </NavLink>}
            </>}
          </li>)}
        </ul>
        {!group.events.length && <p style={{ color: "#667" }}>Brak wydarzeń — dodaj pierwsze powyżej.</p>}
      </>}
    </div>
  );
};

export default ContactGroupDetail;
