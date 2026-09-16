import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

type Interest = { id: number; name: string };
type Education = {
  id: number; institution: string; field_of_study: string | null; degree: string | null;
  start_date: string | null; end_date: string | null; notes: string | null;
};
const degrees: Record<string, string> = {
  bachelor: "Licencjat", engineer: "Inżynier", master: "Magister", doctor: "Doktor", other: "Inne",
};
const emptyEducation = { institution: "", field_of_study: "", degree: "", start_date: "", end_date: "", notes: "" };

export default function ContactInterestsEducation({ contactId, editable, onChanged }: {
  contactId: string; editable: boolean; onChanged: () => void;
}) {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [interests, setInterests] = React.useState<Interest[]>([]);
  const [allInterests, setAllInterests] = React.useState<Interest[]>([]);
  const [selected, setSelected] = React.useState("");
  const [newName, setNewName] = React.useState("");
  const [education, setEducation] = React.useState<Education[]>([]);
  const [form, setForm] = React.useState(emptyEducation);
  const [editingId, setEditingId] = React.useState<number | null>(null);
  const [showForm, setShowForm] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const headers = { "x-api-key": `${apiKey}` };
  const base = `${apiUrl}/contacts/${contactId}`;
  const load = async () => {
    const [contact, dictionary, entries] = await Promise.all([
      axios.get(base, { headers }), axios.get(`${apiUrl}/contact_interests`, { headers }),
      axios.get(`${base}/education`, { headers }),
    ]);
    setInterests(contact.data.contact.interests ?? []);
    setAllInterests(dictionary.data.contact_interests ?? []);
    setEducation(entries.data.education ?? []);
  };
  const run = async (action: () => Promise<void>, changed = true) => {
    setBusy(true); setError("");
    try { await action(); await load(); if (changed) onChanged(); }
    catch (err: any) { setError(err.response?.data?.message || "Nie udało się zapisać lub pobrać danych."); }
    finally { setBusy(false); }
  };
  React.useEffect(() => {
    setInterests([]); setEducation([]); setShowForm(false); setEditingId(null);
    void run(async () => {}, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contactId, apiUrl, apiKey]);
  const saveEducation = () => run(async () => {
    if (editingId === null) await axios.post(`${base}/education`, form, { headers });
    else await axios.patch(`${base}/education/${editingId}`, form, { headers });
    setShowForm(false); setForm(emptyEducation); setEditingId(null);
  });
  return <section style={{ marginTop: 20 }}>
    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    <h3>Hobby i zainteresowania</h3>
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {!interests.length && <span>Brak zainteresowań.</span>}
      {interests.map(interest => <span key={interest.id} style={{ background: "#ecfdf5", borderRadius: 12, padding: "2px 8px" }}>
        <NavLink to={`/contacts?interest_ids=${interest.id}`}>{interest.name}</NavLink>
        {editable && <button type="button" disabled={busy} aria-label={`Usuń zainteresowanie ${interest.name}`}
          onClick={() => void run(async () => { await axios.delete(`${base}/interests/${interest.id}`, { headers }); })}>×</button>}
      </span>)}
    </div>
    {editable && <fieldset disabled={busy} style={{ marginTop: 8 }}>
      <legend>Przypisz zainteresowanie</legend>
      <select aria-label="Zainteresowanie" value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">Wybierz zainteresowanie…</option>
        {allInterests.filter(i => !interests.some(assigned => assigned.id === i.id)).map(i =>
          <option key={i.id} value={i.id}>{i.name}</option>)}
      </select>
      <button type="button" disabled={!selected} onClick={() => void run(async () => {
        await axios.post(`${base}/interests`, { interest_id: Number(selected) }, { headers }); setSelected("");
      })}>Dodaj</button>
      <label> Nowe zainteresowanie <input maxLength={100} value={newName} onChange={e => setNewName(e.target.value)} /></label>
      <button type="button" disabled={!newName.trim()} onClick={() => void run(async () => {
        const response = await axios.post(`${apiUrl}/contact_interests`, { name: newName.trim() }, { headers });
        await axios.post(`${base}/interests`, { interest_id: response.data.contact_interest.id }, { headers }); setNewName("");
      })}>Utwórz i przypisz</button>
    </fieldset>}
    <h3>Wykształcenie</h3>
    {!education.length && <p>Brak wpisów.</p>}
    {education.map(entry => <article key={entry.id} style={{ borderBottom: "1px solid #ddd", padding: 8 }}>
      <strong>{entry.institution}</strong>
      <div>{[entry.field_of_study, entry.degree ? degrees[entry.degree] : null].filter(Boolean).join(" · ")}</div>
      {(entry.start_date || entry.end_date) && <div>{entry.start_date || "?"} — {entry.end_date || "obecnie"}</div>}
      {entry.notes && <p style={{ whiteSpace: "pre-wrap" }}>{entry.notes}</p>}
      {editable && <>
        <button type="button" disabled={busy} onClick={() => {
          setEditingId(entry.id); setForm({ institution: entry.institution, field_of_study: entry.field_of_study ?? "",
            degree: entry.degree ?? "", start_date: entry.start_date ?? "", end_date: entry.end_date ?? "", notes: entry.notes ?? "" });
          setShowForm(true);
        }}>Edytuj</button>
        <button type="button" disabled={busy} onClick={() => {
          if (window.confirm("Usunąć wpis wykształcenia?")) void run(async () => {
            await axios.delete(`${base}/education/${entry.id}`, { headers });
            if (editingId === entry.id) { setShowForm(false); setEditingId(null); }
          });
        }}>Usuń</button>
      </>}
    </article>)}
    {editable && !showForm && <button type="button" disabled={busy} onClick={() => {
      setEditingId(null); setForm(emptyEducation); setShowForm(true);
    }}>Dodaj wykształcenie</button>}
    {editable && showForm && <fieldset disabled={busy}>
      <legend>{editingId === null ? "Nowy wpis" : "Edycja wykształcenia"}</legend>
      <label>Uczelnia / szkoła * <input required maxLength={255} value={form.institution}
        onChange={e => setForm({ ...form, institution: e.target.value })} /></label>
      <label>Kierunek <input maxLength={255} value={form.field_of_study}
        onChange={e => setForm({ ...form, field_of_study: e.target.value })} /></label>
      <label>Stopień <select value={form.degree} onChange={e => setForm({ ...form, degree: e.target.value })}>
        <option value="">Nie podano</option>{Object.entries(degrees).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>Od <input type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} /></label>
      <label>Do <input type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} /></label>
      <label>Notatki <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
      <button type="button" disabled={!form.institution.trim()} onClick={() => void saveEducation()}>Zapisz wykształcenie</button>
      <button type="button" onClick={() => setShowForm(false)}>Anuluj</button>
    </fieldset>}
  </section>;
}
