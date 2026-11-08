import React from "react";
import axios from "axios";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";

interface Candidate { reason: string; score: number; concept: { id: number; name: string; description: string | null } }

interface Props {
  /** The name marked in the text (the "Pojęcia i ideologie" chip). */
  name: string;
  docId: string | number;
  apiUrl: string;
  headers: Record<string, string>;
  /** The concept the name is linked to now: choosing another one replaces that link (it is removed first). */
  current?: { id: number; surface: string } | null;
  onClose: () => void;
  onDone: (message: string) => void;
}

/**
 * Promotes a concept marked in ONE document ("Pojęcia i ideologie" chip) to the registry of concepts: either the
 * name is linked to a concept that already exists (`POST /concepts/mentions/link`, only for this document) or a
 * new one is created under a name and description the reviewer writes here (`POST /concepts`, the marked name
 * becomes its alias) and the name is linked to it. Nothing is written before the button is pressed; a name alone
 * never links anything.
 */
const ConceptRegistryDialog = ({ name, docId, apiUrl, headers, current, onClose, onDone }: Props) => {
  const [title, setTitle] = React.useState(name);
  const [description, setDescription] = React.useState("");
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [target, setTarget] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const numericDocId = Number(docId);

  const lookup = React.useCallback(async (text: string) => {
    const query = text.trim();
    if (!query) { setCandidates([]); return; }
    try {
      const { data } = await axios.get<{ candidates: Candidate[] }>(
        `${apiUrl}/concepts/candidates`, { headers, params: { name: query } },
      );
      setCandidates(data.candidates ?? []);
      setTarget(null);
    } catch {
      setCandidates([]);
    }
  }, [apiUrl, headers]);

  React.useEffect(() => {
    void lookup(name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const canSubmit = !busy && Number.isInteger(numericDocId) && (target !== null || title.trim() !== "");

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const startedAt = Date.now();
    try {
      let conceptId = target;
      let conceptName = candidates.find((c) => c.concept.id === target)?.concept.name ?? title.trim();
      if (conceptId === null) {
        const { data } = await axios.post<{ concept: { id: number; name: string } }>(`${apiUrl}/concepts`, {
          name: title.trim(), aliases: [name], ...(description.trim() && { description: description.trim() }),
        }, { headers });
        conceptId = data.concept.id;
        conceptName = data.concept.name;
      }
      if (current && current.id !== conceptId) {
        await axios.post(`${apiUrl}/concepts/mentions/unlink`,
          { name: current.surface, concept_id: current.id, document_id: numericDocId }, { headers });
      }
      await axios.post(`${apiUrl}/concepts/mentions/link`,
        { name, concept_id: conceptId, document_ids: [numericDocId] }, { headers });
      onDone(`„${name}” jest teraz powiązane z pojęciem #${conceptId} ${conceptName}.`);
    } catch (err) {
      setError(describeRequestError(err, "Dodawanie pojęcia do rejestru", {
        startedAt, context: { dokument: docId, nazwa: name },
      }));
      setBusy(false);
    }
  };

  return (
    <div role="dialog" aria-label={`Rejestr pojęć: ${name}`}
      style={{
        position: "fixed", left: "50%", top: 80, transform: "translateX(-50%)", zIndex: 1000, width: "min(560px, 92vw)",
        padding: 14, background: "#fff", border: "1px solid #94a3b8", borderRadius: 8, boxShadow: "0 6px 24px rgba(0,0,0,0.3)",
      }}>
      <strong>💡 {name}</strong>
      <p style={{ margin: "4px 0 8px", color: "#64748b", fontSize: "0.9em" }}>
        {current && <strong>Teraz powiązane z pojęciem #{current.id}. </strong>}
        Zaznaczona nazwa to jeszcze nie wpis w rejestrze. Tu wiążesz ją z pojęciem z rejestru (<code>/concepts</code>)
        albo tworzysz nowe, z opisem; powiązanie dotyczy tego dokumentu.
      </p>
      <label style={{ display: "block", marginBottom: 6 }}>
        Nazwa pojęcia
        <input type="text" value={title} disabled={target !== null} style={{ width: "100%", padding: "4px 6px", boxSizing: "border-box" }}
          onChange={(e) => setTitle(e.target.value)} onBlur={() => void lookup(title)} />
      </label>
      <label style={{ display: "block", marginBottom: 6 }}>
        Opis (czym jest, skąd pochodzi, kto je głosi)
        <textarea value={description} rows={4} disabled={target !== null}
          style={{ width: "100%", padding: "4px 6px", boxSizing: "border-box" }}
          onChange={(e) => setDescription(e.target.value)} />
      </label>
      <button type="button" onClick={() => void lookup(title)} style={{ marginBottom: 6 }}>
        🔎 Sprawdź, czy już jest w rejestrze
      </button>
      {candidates.length > 0 && (
        <fieldset style={{ margin: "4px 0", border: "1px solid #e2e8f0" }}>
          <legend>Czy to to samo pojęcie?</legend>
          <label style={{ display: "block" }}>
            <input type="radio" name="concept-target" checked={target === null} onChange={() => setTarget(null)} />
            {" "}Nie, utwórz nowe pojęcie
          </label>
          {candidates.map((c) => (
            <label key={c.concept.id} style={{ display: "block" }}>
              <input type="radio" name="concept-target" checked={target === c.concept.id} onChange={() => setTarget(c.concept.id)} />
              {" "}Tak, powiąż z: #{c.concept.id} {c.concept.name}
              <small style={{ color: "#64748b" }}>
                {" "}({c.reason === "alias" ? "ta sama nazwa" : `podobna nazwa ${c.score}`})
              </small>
            </label>
          ))}
        </fieldset>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button type="button" disabled={!canSubmit} onClick={() => void submit()}>
          {busy ? "⏳ Zapisuję…" : target !== null ? "Powiąż z pojęciem" : "Utwórz pojęcie i powiąż"}
        </button>
        <button type="button" disabled={busy} onClick={onClose}>Anuluj</button>
      </div>
      {error && (
        <div role="alert" style={{ color: "#a33" }}>
          <p>{error.summary}</p>
          <RequestErrorDetails details={error.details} />
        </div>
      )}
    </div>
  );
};

export default ConceptRegistryDialog;
