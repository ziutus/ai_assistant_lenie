import React from "react";
import axios from "axios";

interface Props {
  entityId: number;
  name: string;
  description: string | null;
  apiUrl: string;
  headers: Record<string, string>;
  onClose: () => void;
  onSaved: () => void;
}

// Description of a hand-added event: the LLM drafts it from the sentences that mention the event
// (POST /website_entities/:id/describe, nothing stored), the reviewer edits it and only "Zapisz"
// stores it (PUT /website_entities/:id/description).
const EventDescriptionDialog = ({ entityId, name, description, apiUrl, headers, onClose, onSaved }: Props) => {
  const [text, setText] = React.useState(description ?? "");
  const [sentences, setSentences] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [notice, setNotice] = React.useState("");
  const [error, setError] = React.useState("");

  const generate = React.useCallback(async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${entityId}/describe`, {}, { headers });
      setSentences(response.data.sentences ?? []);
      if (response.data.description) setText(response.data.description);
      else setNotice("Model uznał, że zdania z tekstu nie wystarczają do opisu — wpisz go ręcznie.");
    } catch (failure) {
      setError(axios.isAxiosError(failure) ? failure.response?.data?.message ?? "Nie udało się wygenerować opisu." : "Nie udało się wygenerować opisu.");
    } finally {
      setBusy(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, entityId]);

  React.useEffect(() => {
    if (!description) void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await axios.put(`${apiUrl}/website_entities/${entityId}/description`, { description: text }, { headers });
      onSaved();
    } catch {
      setError("Nie udało się zapisać opisu.");
      setBusy(false);
    }
  };

  return (
    <div role="dialog" aria-label={`Opis wydarzenia ${name}`}
      style={{
        position: "fixed", left: "50%", top: 80, transform: "translateX(-50%)", zIndex: 1000, width: "min(560px, 92vw)",
        padding: 14, background: "#fff", border: "1px solid #94a3b8", borderRadius: 8, boxShadow: "0 6px 24px rgba(0,0,0,0.3)",
      }}>
      <strong>📅 {name}</strong>
      <label style={{ display: "block", marginTop: 8 }}>Opis wydarzenia
        <textarea value={text} rows={4} maxLength={2000} aria-label="Opis wydarzenia" disabled={busy}
          onChange={(event) => setText(event.target.value)} style={{ width: "100%", boxSizing: "border-box" }} />
      </label>
      {busy && <p role="status" style={{ margin: "4px 0", color: "#64748b" }}>Pracuję…</p>}
      {notice && <p role="status" style={{ margin: "4px 0", color: "#92400e" }}>{notice}</p>}
      {error && <p role="alert" style={{ margin: "4px 0", color: "#a33" }}>{error}</p>}
      {sentences.length > 0 && (
        <details style={{ marginTop: 6, fontSize: "0.85em" }}>
          <summary>Zdania użyte jako źródło ({sentences.length})</summary>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{sentences.map((sentence) => <li key={sentence}>{sentence}</li>)}</ul>
        </details>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button type="button" disabled={busy} onClick={() => void generate()}>🤖 Wygeneruj opis</button>
        <button type="button" disabled={busy} onClick={() => void save()}>Zapisz</button>
        <button type="button" onClick={onClose}>Zamknij</button>
      </div>
    </div>
  );
};

export default EventDescriptionDialog;
