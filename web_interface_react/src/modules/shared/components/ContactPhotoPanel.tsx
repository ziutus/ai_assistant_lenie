import React from "react";
import axios from "axios";
import ContactPhotoDescriptions, { type ContactPhotoData } from "./ContactPhotoDescriptions";

interface PhotoDetails extends ContactPhotoData {
  photo_url: string | null;
  contacts: { contact_id: number; display_name: string; depicts_contact: boolean | null; link_revision: number }[];
}

interface Props {
  photoId: string;
  contactId: string;
  apiUrl: string;
  apiKey: string;
  onClose: () => void;
  onChange: (photo: ContactPhotoData) => void;
}

export default function ContactPhotoPanel({ photoId, contactId, apiUrl, apiKey, onClose, onChange }: Props) {
  const [photo, setPhoto] = React.useState<PhotoDetails | null>(null);
  const [kind, setKind] = React.useState("unknown");
  const [count, setCount] = React.useState("");
  const [depicts, setDepicts] = React.useState("unknown");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [suggested, setSuggested] = React.useState(false);
  const dialog = React.useRef<HTMLDialogElement>(null);
  const base = `${apiUrl}/contact_photos/${photoId}`;
  const headers = { "x-api-key": apiKey };
  const load = async (initialize = false) => {
    const response = await axios.get<PhotoDetails>(base, { headers });
    const data = response.data;
    setPhoto(data);
    if (initialize) {
      setKind(data.subject_kind ?? "unknown");
      setCount(data.people_count == null ? "" : String(data.people_count));
      const value = data.contacts.find((c) => String(c.contact_id) === contactId)?.depicts_contact;
      setDepicts(value == null ? "unknown" : String(value));
    }
  };
  React.useEffect(() => {
    dialog.current?.showModal();
    void load(true).catch(() => setError("Nie udało się pobrać zdjęcia."));
  }, [photoId]);
  const changed = (updated: ContactPhotoData) => {
    setPhoto((previous) => previous && ({ ...previous, ...updated }));
    onChange(updated);
  };
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await action(); } catch (failure: any) {
      setError(failure.response?.data?.message ?? "Nie udało się wykonać operacji.");
      if (failure.response?.status === 409) {
        try { await load(); } catch { setError("Konflikt zapisu. Nie udało się odświeżyć danych; szkic zachowano."); }
      }
    } finally { setBusy(false); }
  };
  const link = photo?.contacts.find((c) => String(c.contact_id) === contactId);
  const others = photo?.contacts.filter((c) => String(c.contact_id) !== contactId) ?? [];
  return <dialog ref={dialog} aria-label="Szczegóły zdjęcia" onCancel={onClose}
    style={{ maxWidth: 900, width: "90vw", maxHeight: "90vh", overflow: "auto" }}>
    <button type="button" onClick={onClose}>Zamknij</button>
    <h2>Szczegóły zdjęcia</h2>
    {error && <p role="alert">{error}</p>}
    {!photo && !error && <p role="status">Ładowanie zdjęcia…</p>}
    {photo && <>
      {photo.photo_url && <img src={photo.photo_url} alt="Podgląd zdjęcia" style={{ width: "100%", maxHeight: 500, objectFit: "contain" }} />}
      <p>Zmiana opisu i klasyfikacji dotyczy {photo.contacts.length} kontaktów: {photo.contacts.map((c) => c.display_name).join(", ")}.</p>
      {others.length > 0 && <p>Inne kontakty współdzielące zdjęcie: {others.map((c) => c.display_name).join(", ")}.</p>}
      <ContactPhotoDescriptions photo={photo} contactId={contactId} apiUrl={apiUrl} apiKey={apiKey}
        onChange={changed} onConflict={() => load()} />
      <h3>Klasyfikacja zdjęcia</h3>
      <label>Temat zdjęcia <select value={kind} onChange={(e) => {
        setKind(e.target.value); if (e.target.value === "no_people") setCount("");
      }}>
        <option value="people">Ludzie</option><option value="no_people">Bez ludzi</option><option value="unknown">Nieustalone</option>
      </select></label>
      <label>Liczba osób <input type="number" min="0" step="1" value={count} disabled={kind === "no_people"}
        onChange={(e) => setCount(e.target.value)} /></label>
      <p>Pusta liczba oznacza, że nie została ustalona. Propozycja AI kosztuje jedno wywołanie LLM.</p>
      <button type="button" disabled={busy} onClick={() => void run(async () => {
        const response = await axios.post(`${base}/classify/suggest`, {}, { headers });
        setKind(response.data.subject_kind);
        setCount(response.data.people_count == null ? "" : String(response.data.people_count));
        setSuggested(true);
      })}>Zaproponuj klasyfikację (AI)</button>
      {suggested && <p role="status">Propozycja AI jest w formularzu. Sprawdź ją i kliknij Zapisz klasyfikację.</p>}
      <button type="button" disabled={busy} onClick={() => void run(async () => {
        const response = await axios.patch(`${base}/classification`, {
          subject_kind: kind, people_count: kind === "no_people" || count === "" ? null : Number(count),
          classification_revision: photo.classification_revision,
        }, { headers });
        changed(response.data.photo); setSuggested(false);
      })}>Zapisz klasyfikację</button>
      {link && <section>
        <label>Zdjęcie przedstawia tę osobę <select value={depicts} onChange={(e) => setDepicts(e.target.value)}>
          <option value="true">Tak</option><option value="false">Nie</option><option value="unknown">Nie wiem</option>
        </select></label>
        <button type="button" disabled={busy} onClick={() => void run(async () => {
          const response = await axios.patch(`${base}/contacts/${contactId}`, {
            depicts_contact: depicts === "unknown" ? null : depicts === "true", revision: link.link_revision,
          }, { headers });
          const updated = { ...photo, depicts_contact: response.data.depicts_contact, link_revision: response.data.revision,
            contacts: photo.contacts.map((c) => c === link ? { ...c, depicts_contact: response.data.depicts_contact, link_revision: response.data.revision } : c) };
          changed(updated);
        })}>Zapisz powiązanie</button>
      </section>}
    </>}
  </dialog>;
}
