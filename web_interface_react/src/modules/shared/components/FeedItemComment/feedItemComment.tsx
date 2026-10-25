import React from "react";
import { Link } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";
import { ACTION_TIMEOUT_MS, describeActionError, fetchWithTimeout } from "../../pages/feedReview";

type Props = {
  itemId: number;
  initialNote: string | null | undefined;
  onSaved: (note: string) => void;
  buildBrief: (comment: string) => string;
  seedDocumentId?: number | null;
  onSeedCreated?: (documentId: number) => void;
};

// The parent keys this editor by item ID, keeping drafts isolated between cards.
export default function FeedItemComment({ itemId, initialNote, onSaved, buildBrief, seedDocumentId, onSeedCreated }: Props) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [note, setNote] = React.useState(initialNote ?? "");
  const [savedNote, setSavedNote] = React.useState(initialNote ?? "");
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState("");
  const inputId = React.useId();
  const dirty = note !== savedNote;

  const createSeed = async () => {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const response = await fetchWithTimeout(`${apiUrl}/feed_items/${itemId}/seed_document`, {
        method: "POST",
        headers: { "x-api-key": apiKey || "", "Content-Type": "application/json" },
      }, ACTION_TIMEOUT_MS);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.error || `Nie udało się utworzyć zalążka dokumentu (${response.status}).`);
      onSeedCreated?.(data.document_id);
      setMessage(data.created ? "Utworzono zalążek dokumentu." : "Zalążek już istniał.");
    } catch (cause) {
      setError(cause instanceof TypeError
        ? "Nie można połączyć się z API - zalążek dokumentu NIE został utworzony."
        : describeActionError(cause, apiUrl, "Nie udało się utworzyć zalążka dokumentu."));
    } finally { setSaving(false); }
  };

  const save = async () => {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const response = await fetchWithTimeout(`${apiUrl}/feed_items/${itemId}/note`, {
        method: "PATCH",
        headers: { "x-api-key": apiKey || "", "Content-Type": "application/json" },
        body: JSON.stringify({ note }),
      }, ACTION_TIMEOUT_MS);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.error || `Nie udało się zapisać komentarza (${response.status}).`);
      const saved = data.review_note ?? "";
      setSavedNote(saved);
      setNote(saved);
      onSaved(saved);
      setMessage(saved ? "Zapisano komentarz." : "Usunięto komentarz.");
    } catch (cause) {
      setError(cause instanceof TypeError
        ? "Nie można połączyć się z API - komentarz NIE został zapisany."
        : describeActionError(cause, apiUrl, "Nie udało się zapisać komentarza."));
    } finally { setSaving(false); }
  };

  const copy = async () => {
    setMessage("");
    setError("");
    try {
      const brief = buildBrief(note);
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(brief);
      else {
        const textarea = document.createElement("textarea");
        const focused = document.activeElement;
        textarea.value = brief;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        try {
          textarea.select();
          if (!document.execCommand("copy")) throw new Error("Copy failed");
        } finally {
          textarea.remove();
          if (focused instanceof HTMLElement) focused.focus();
        }
      }
      setMessage("Skopiowano brief - wklej go do czatu LLM.");
    } catch { setError("Nie udało się skopiować briefu - spróbuj ponownie."); }
  };

  return <div style={{ margin: "12px 0" }}>
    <label htmlFor={inputId}>Komentarz dla LLM: co mnie zainteresowało i co z tym zrobić</label>
    <textarea id={inputId} rows={3} maxLength={4000} value={note} disabled={saving}
      aria-describedby={`${inputId}-count`} style={{ display: "block", width: "100%", boxSizing: "border-box" }}
      placeholder="Np. Interesuje mnie, że istnieje taka inicjatywa; chcę stworzyć zalążek dokumentu o niej i kontynuować z ChatGPT / Claude Code."
      onChange={event => { setNote(event.target.value); setMessage(""); setError(""); }} />
    <div id={`${inputId}-count`}>{note.length}/4000 {dirty && <span>● niezapisane zmiany</span>}</div>
    <button type="button" disabled={!dirty || saving} onClick={() => void save()}>Zapisz komentarz</button>{" "}
    <button type="button" onClick={() => void copy()}>Skopiuj brief dla LLM</button>
    {" "}{seedDocumentId != null
      ? <span>Zalążek dokumentu: <Link to={`/text/${seedDocumentId}`}>Otwórz #{seedDocumentId}</Link></span>
      : <button type="button" disabled={dirty || saving} title={dirty ? "Najpierw zapisz komentarz" : undefined}
        onClick={() => void createSeed()}>Utwórz zalążek dokumentu</button>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
