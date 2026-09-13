import React from "react";
import axios from "axios";
import type { ContactPhotoData } from "./ContactPhotoDescriptions";

interface Member { first_name: string; last_name: string; display_label: string }
interface Props {
  contactId: string;
  contactName: string;
  photo: ContactPhotoData;
  apiUrl: string;
  apiKey: string;
  groups: { id: number; name: string }[];
  onCreated: () => void;
}

// crypto.randomUUID requires a secure context; Lenie also runs over LAN HTTP.
function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export default function ContactFamilyForm({ contactId, contactName, photo, apiUrl, apiKey, groups, onCreated }: Props) {
  const member = (label: string): Member => ({ first_name: "", last_name: "", display_label: `${label} — ${contactName}` });
  const [open, setOpen] = React.useState(false);
  const [spouse, setSpouse] = React.useState(() => member("Drugi rodzic"));
  const [includeSpouse, setIncludeSpouse] = React.useState(true);
  const [spouseRelation, setSpouseRelation] = React.useState("mąż");
  const [children, setChildren] = React.useState(() => [member("Dziecko 1"), member("Dziecko 2")]);
  const [twins, setTwins] = React.useState(false);
  const [sharePhoto, setSharePhoto] = React.useState(true);
  const [copyGroups, setCopyGroups] = React.useState(true);
  const [childrenGroup, setChildrenGroup] = React.useState("");
  const [sourceNote, setSourceNote] = React.useState("");
  const [peerQuery, setPeerQuery] = React.useState("");
  const [peerResults, setPeerResults] = React.useState<{ id: number; display_name: string }[]>([]);
  const [peerId, setPeerId] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [searching, setSearching] = React.useState(false);
  const [error, setError] = React.useState("");
  const [result, setResult] = React.useState<{ spouse: { id: number; display_name: string } | null; children: { id: number; display_name: string }[] } | null>(null);
  const attempt = React.useRef<{ signature: string; id: string } | null>(null);
  const headers = { "x-api-key": apiKey };

  const searchPeers = async () => {
    setSearching(true);
    setError("");
    try {
      const response = await axios.get(`${apiUrl}/contacts`, { params: { q: peerQuery, limit: 30 }, headers });
      setPeerResults((response.data.contacts ?? []).filter((item: { id: number }) => String(item.id) !== contactId));
      setPeerId("");
    } catch {
      setError("Nie udało się wyszukać kontaktów.");
    } finally { setSearching(false); }
  };

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const payload = {
      storage_key: photo.storage_key,
      spouse: includeSpouse ? spouse : null,
      spouse_relationship: spouseRelation,
      children, twins, share_photo: sharePhoto, copy_parent_groups: copyGroups,
      source_note: sourceNote,
      peer_contact_id: peerId ? Number(peerId) : null,
      children_group_id: childrenGroup ? Number(childrenGroup) : null,
    };
    const signature = JSON.stringify(payload);
    if (!attempt.current || attempt.current.signature !== signature) attempt.current = { signature, id: requestId() };
    try {
      const response = await axios.post(`${apiUrl}/contacts/${contactId}/family`, {
        ...payload, request_id: attempt.current.id,
      }, { headers });
      setResult(response.data.family);
      onCreated();
    } catch (error: any) {
      setError(error.response?.data?.message ?? "Nie udało się potwierdzić zapisu. Ponowienie bez zmiany formularza nie utworzy duplikatów.");
    } finally { setBusy(false); }
  };

  const fields = (value: Member, update: (next: Member) => void, title: string) => <fieldset style={{ marginBottom: 10 }}>
    <legend>{title}</legend>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
      <label>Imię <input maxLength={100} value={value.first_name} onChange={(e) => update({ ...value, first_name: e.target.value })} /></label>
      <label>Nazwisko <input maxLength={100} value={value.last_name} onChange={(e) => update({ ...value, last_name: e.target.value })} /></label>
      <label>Nazwa robocza <input maxLength={200} value={value.display_label} onChange={(e) => update({ ...value, display_label: e.target.value })} /></label>
    </div>
  </fieldset>;

  if (result) return <section aria-label="Utworzona rodzina">
    <p role="status">Zapisano rodzinę i powiązania.</p>
    <ul>{[...(result.spouse ? [result.spouse] : []), ...result.children].map((item) =>
      <li key={item.id}><a href={`/contacts/${item.id}`}>{item.display_name}</a></li>)}</ul>
  </section>;

  return <section aria-label="Tworzenie rodziny" style={{ marginTop: 16, marginBottom: 20 }}>
    <button type="button" className="button" onClick={() => {
      if (!open && !sourceNote) setSourceNote(photo.user_description ?? "");
      setOpen(!open);
    }}>{open ? "Zwiń formularz rodziny" : "Utwórz kontakty członków rodziny"}</button>
    {open && <form onSubmit={create} style={{ marginTop: 12 }}>
      <p>Uzupełnij znane informacje. Imiona i nazwiska mogą pozostać puste — nazwy robocze pozwolą wrócić do tych samych osób później.</p>
      <p>„Dziecko 1” i „Dziecko 2” to osobne rekordy; numery nie wskazują położenia dzieci na zdjęciu.</p>
      <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
        <label><input type="checkbox" checked={includeSpouse} onChange={(e) => setIncludeSpouse(e.target.checked)} /> Utwórz kontakt drugiego rodzica</label>
        {includeSpouse && <>
          <p><label>Relacja do {contactName}: <select value={spouseRelation} onChange={(e) => setSpouseRelation(e.target.value)}>
            {["mąż", "żona", "partner", "partnerka"].map((value) => <option key={value}>{value}</option>)}
          </select></label></p>
          {fields(spouse, setSpouse, "Drugi rodzic")}
          <p><label><input type="checkbox" checked={copyGroups} onChange={(e) => setCopyGroups(e.target.checked)} /> Dodaj drugiego rodzica do grup tego kontaktu</label></p>
        </>}
        {children.map((child, index) => <React.Fragment key={index}>
          {fields(child, (next) => setChildren((old) => old.map((item, i) => i === index ? next : item)), `Dziecko ${index + 1}`)}
        </React.Fragment>)}
        <button type="button" disabled={children.length >= 6 || twins} onClick={() => setChildren([...children, member(`Dziecko ${children.length + 1}`)])}>Dodaj dziecko</button>{" "}
        <button type="button" disabled={children.length <= 1 || twins} onClick={() => setChildren(children.slice(0, -1))}>Usuń ostatnie dziecko z formularza</button>
        <p><label><input type="checkbox" checked={twins} disabled={children.length !== 2} onChange={(e) => setTwins(e.target.checked)} /> Wiem, że te dzieci są bliźniętami</label></p>
        <p><label><input type="checkbox" checked={sharePhoto} onChange={(e) => setSharePhoto(e.target.checked)} /> Przypisz to samo zdjęcie i jego opisy wszystkim nowym kontaktom</label></p>
        <p><label>Grupa dzieci: <select value={childrenGroup} onChange={(e) => setChildrenGroup(e.target.value)}>
          <option value="">Bez przypisania do grupy kontaktów</option>
          {groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}
        </select></label></p>
        <p>Dzieci nie dziedziczą grup rodzica. Możesz wskazać dla nich osobną grupę.</p>
        <label>Znane dziecko z tej samej grupy przedszkolnej (np. Filip) <input value={peerQuery} onChange={(e) => { setPeerQuery(e.target.value); setPeerId(""); setPeerResults([]); }} /></label>{" "}
        <button type="button" disabled={searching || !peerQuery.trim()} onClick={searchPeers}>Wyszukaj dziecko</button>
        <p><label>Powiąż z kontaktem: <select value={peerId} onChange={(e) => setPeerId(e.target.value)}>
          <option value="">Bez powiązania z innym dzieckiem</option>
          {peerResults.map((peer) => <option value={peer.id} key={peer.id}>{peer.display_name} (#{peer.id})</option>)}
        </select></label></p>
        <label>Twoja informacja potwierdzająca relacje rodzinne
          <textarea required maxLength={12000} rows={4} value={sourceNote} onChange={(e) => setSourceNote(e.target.value)} style={{ width: "100%", boxSizing: "border-box" }} />
        </label>
        <p>Zostanie utworzonych {children.length + (includeSpouse ? 1 : 0)} kontaktów. Każde dziecko będzie powiązane z {includeSpouse ? "obojgiem rodziców" : contactName}{twins ? "; dzieci połączy też relacja bliźniąt" : ""}.</p>
        <button type="submit" className="button">{busy ? "Zapisywanie rodziny…" : "Utwórz rodzinę i powiązania"}</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </form>}
  </section>;
}
