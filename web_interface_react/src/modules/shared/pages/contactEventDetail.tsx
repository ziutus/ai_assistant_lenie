import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { formatEventDateRange } from "../utils/contactEventDate";
import type { ContactGroupEvent } from "./contactGroupDetail";
import type { ContactGroup } from "./contactGroups";

type Participant = ContactGroupEvent["participants"][number];
interface EventForm {
  title: string;
  event_date: string;
  event_date_end: string;
  summary: string;
  group_id: number | null;
  participants: Participant[];
}
const emptyForm: EventForm = { title: "", event_date: "", event_date_end: "", summary: "", group_id: null, participants: [] };
const rowStyle: React.CSSProperties = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" };
const chipStyle: React.CSSProperties = { display: "inline-block", padding: "2px 8px", borderRadius: 12, background: "#eef2ff" };

const toForm = (event: ContactGroupEvent): EventForm => ({
  title: event.title, event_date: event.event_date, event_date_end: event.event_date_end ?? "",
  summary: event.summary ?? "", group_id: event.group_id, participants: [...event.participants],
});

const ContactEventDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const validId = !!id && /^\d+$/.test(id) && Number.isSafeInteger(Number(id)) && Number(id) > 0;
  const [event, setEvent] = React.useState<ContactGroupEvent | null>(null);
  const [groups, setGroups] = React.useState<ContactGroup[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState("");
  const [groupError, setGroupError] = React.useState("");
  const [editing, setEditing] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [form, setForm] = React.useState<EventForm>(emptyForm);
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<Participant[]>([]);
  const [targetId, setTargetId] = React.useState<number | null>(null);
  const [searching, setSearching] = React.useState(false);
  const searchVersion = React.useRef(0);
  const requestVersion = React.useRef(0);
  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };
  const report = (text: string, error = false) => { setMessage(text); setIsError(error); };
  const resetPicker = () => {
    searchVersion.current += 1;
    setQuery(""); setResults([]); setTargetId(null); setSearching(false);
  };

  React.useEffect(() => {
    let cancelled = false;
    requestVersion.current += 1;
    setEvent(null); setGroups([]); setEditing(false); setBusy(false);
    setForm(emptyForm); resetPicker(); report(""); setLoadError(""); setGroupError("");
    setIsLoading(validId);
    if (validId) {
      axios.get(`${apiUrl}/contact_group_events/${id}`, { headers }).then(response => {
        if (!cancelled) { setEvent(response.data.event); setForm(toForm(response.data.event)); }
      }).catch(error => {
        if (!cancelled) setLoadError(error.response?.status === 404
          ? "Nie znaleziono wydarzenia."
          : `Nie udało się pobrać wydarzenia: ${error.response?.data?.message || error.message}`);
      }).finally(() => { if (!cancelled) setIsLoading(false); });
      axios.get(`${apiUrl}/contact_groups`, { headers }).then(response => {
        if (!cancelled) setGroups(response.data.contact_groups);
      }).catch(error => {
        if (!cancelled) setGroupError(`Nie udało się pobrać grup: ${error.response?.data?.message || error.message}`);
      });
    }
    return () => { cancelled = true; searchVersion.current += 1; requestVersion.current += 1; };
  }, [id, apiUrl, apiKey]);

  const cancelEdit = () => {
    if (event) setForm(toForm(event));
    resetPicker(); setEditing(false); report("");
  };

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
    if (busy) return;
    if (!form.title.trim() || !form.event_date) {
      report("Tytuł i data są wymagane.", true); return;
    }
    if (form.event_date_end && form.event_date_end < form.event_date) {
      report("Data zakończenia nie może być wcześniejsza niż data rozpoczęcia.", true); return;
    }
    if (form.group_id === null && !form.participants.length) {
      report("Wydarzenie musi być powiązane z grupą lub co najmniej jednym kontaktem.", true); return;
    }
    const version = requestVersion.current;
    setBusy(true); resetPicker(); report("");
    try {
      const response = await axios.patch(`${apiUrl}/contact_group_events/${id}`, {
        title: form.title, event_date: form.event_date, event_date_end: form.event_date_end || null,
        group_id: form.group_id, summary: form.summary,
        participant_contact_ids: form.participants.map(contact => contact.id),
      }, { headers });
      if (version !== requestVersion.current) return;
      setEvent(response.data.event); setForm(toForm(response.data.event)); setEditing(false);
      report("Zapisano wydarzenie.");
    } catch (error: any) {
      if (version === requestVersion.current) report(`Nie udało się zapisać: ${error.response?.data?.message || error.message}`, true);
    } finally { if (version === requestVersion.current) setBusy(false); }
  };

  const remove = async () => {
    if (busy || !event || !window.confirm(`Usunąć wydarzenie „${event.title}”?`)) return;
    const version = requestVersion.current;
    setBusy(true); resetPicker(); report("");
    try {
      await axios.delete(`${apiUrl}/contact_group_events/${id}`, { headers });
      if (version === requestVersion.current) navigate("/contact-events");
    } catch (error: any) {
      if (version === requestVersion.current) report(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`, true);
    } finally { if (version === requestVersion.current) setBusy(false); }
  };
  const availableResults = results.filter(result => !form.participants.some(contact => contact.id === result.id));

  return <div>
    <NavLink to="/contact-events">← Wydarzenia</NavLink>
    {!validId ? <p role="alert">Nieprawidłowy lub brakujący identyfikator wydarzenia.</p>
      : isLoading ? <p>Ładowanie…</p>
      : loadError ? <p role="alert">{loadError}</p>
      : event && <>
        {message && <p role={isError ? "alert" : "status"} style={{ color: isError ? "#b91c1c" : "#166534" }}>{message}</p>}
        {groupError && <p role="alert">{groupError}</p>}
        {editing ? (
          <form onSubmit={event => { event.preventDefault(); void save(); }}>
            <fieldset disabled={busy || isLoading} style={{ border: "1px solid #d5dde8", borderRadius: 6, padding: 12 }}>
              <legend>Edytuj wydarzenie</legend>
              <div style={rowStyle}>
                <label>Tytuł <input required maxLength={255} value={form.title}
                  onChange={event => setForm({ ...form, title: event.target.value })} /></label>
                <label>Data <input required type="date" value={form.event_date}
                  onChange={event => setForm({ ...form, event_date: event.target.value })} /></label>
                <label>Data zakończenia (opcjonalnie) <input type="date" min={form.event_date || ""} value={form.event_date_end}
                  onChange={event => setForm({ ...form, event_date_end: event.target.value })} /></label>
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
              <button className="button" type="submit">{busy ? "Zapisywanie…" : "Zapisz"}</button>{" "}
              <button className="button" type="button" onClick={cancelEdit}>Anuluj</button>
            </fieldset>
          </form>
        ) : <>
          <h2>{event.title}</h2>
          <p><time dateTime={event.event_date}>{formatEventDateRange(event.event_date, event.event_date_end)}</time></p>
          <div style={rowStyle}>
            {event.group_id !== null && <NavLink style={chipStyle} to={`/contact_groups/${event.group_id}`}>{event.group_name}</NavLink>}
            {event.participants.map(contact => <NavLink key={contact.id} style={chipStyle} to={`/contacts/${contact.id}`}>
              {contact.display_name}
            </NavLink>)}
          </div>
          {event.summary && <p style={{ whiteSpace: "pre-wrap" }}>{event.summary}</p>}
          {event.source_document_id !== null && <p><NavLink to={`/read/${event.source_document_id}`}>
            {event.source_document_title || `Dokument #${event.source_document_id}`}
          </NavLink></p>}
          <p><button className="button" disabled={busy} onClick={() => {
            setForm(toForm(event)); resetPicker(); report(""); setEditing(true);
          }}>Edytuj</button></p>
        </>}
        <button className="button" disabled={busy} onClick={remove}>Usuń</button>
      </>}
  </div>;
};

export default ContactEventDetail;
