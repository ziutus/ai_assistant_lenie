import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";

interface Section {
  position: number;
  title: string;
  sentence_count: number;
  char_length: number;
  first_sentences: string[];
  last_sentences: string[];
}

interface Props {
  docId: string;
  disabled?: boolean;
  onSaved: () => Promise<unknown>;
}

function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const message = String(error.response?.data?.message || "");
    if (error.response?.status === 409) {
      return message.includes("embeddings")
        ? "Dokument ma embeddingi — otwórz go ponownie do edycji przed zmianą granic rozdziałów."
        : "Trwa analiza dokumentu. Poczekaj na jej zakończenie i spróbuj ponownie.";
    }
    if (error.response?.status === 400 && message && !message.startsWith("Document")) return message;
  }
  return "Nie udało się zmienić lub pobrać granic rozdziałów. Spróbuj ponownie.";
}

export default function ChapterBoundariesPanel({ docId, disabled = false, onSaved }: Props) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [sections, setSections] = React.useState<Section[]>([]);
  const [busy, setBusy] = React.useState(false);
  const pending = React.useRef(false);
  const [error, setError] = React.useState("");
  const [steps, setSteps] = React.useState(1);
  const [hasEmbeddings, setHasEmbeddings] = React.useState(false);
  const [stale, setStale] = React.useState(false);
  const headers = { "x-api-key": apiKey };

  const load = async () => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      const { data } = await axios.get(apiUrl + "/document/" + docId + "/chapter_sections", { headers });
      setSections(data.sections);
      setHasEmbeddings(data.has_embeddings);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  const move = async (position: number, sentences: number) => {
    if (pending.current || disabled) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      const { data } = await axios.post(apiUrl + "/document/" + docId + "/move_chapter_boundary",
        { position, sentences }, { headers });
      setSections(data.sections);
      setHasEmbeddings(data.has_embeddings);
      if (data.stale_analysis_runs > 0) setStale(true);
      await onSaved();
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  return (
    <details style={{ marginBottom: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}
      onToggle={event => { if (event.currentTarget.open) void load(); }}>
      <summary style={{ cursor: "pointer", fontWeight: "bold" }}>Granice rozdziałów</summary>
      <p>Zapisuje od razu w bazie. Po przesunięciu formularz zostanie odświeżony — wcześniej zapisz inne zmiany.</p>
      {hasEmbeddings && <p role="status">Dokument ma embeddingi — otwórz go ponownie do edycji przed zmianą granic rozdziałów.</p>}
      {stale && <p role="status" style={{ color: "#92400e" }}>
        Rozdziały w czytniku zostały zaktualizowane. Istniejące chunki (<NavLink to={"/chunks/" + docId}>{"/chunks/" + docId}</NavLink>) powstały ze starego podziału — uruchom analizę ponownie.
      </p>}
      {error && <p role="alert">{error} <button type="button" onClick={load} disabled={busy}>Odśwież</button></p>}
      {busy && <p role="status">Przetwarzam…</p>}
      <label>Liczba zdań: <select value={steps} disabled={busy || disabled} onChange={event => setSteps(Number(event.target.value))}>
        {[1, 3, 5].map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      {!busy && !error && sections.length > 0 && !sections.some(section => section.position >= 2)
        && <p>Potrzebne są co najmniej dwa rozdziały.</p>}
      {sections.filter(section => section.position >= 2).map(section => {
        const previous = sections.find(item => item.position === section.position - 1)!;
        const blocked = busy || disabled || hasEmbeddings;
        return <section key={section.position} aria-label={"Granica: " + section.title}
          style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid #cbd5e1" }}>
          <small>Koniec poprzedniego rozdziału: {previous.title}</small>
          <p style={{ whiteSpace: "pre-wrap" }}>{previous.last_sentences.join(" ")}</p>
          <h3>{section.title}</h3>
          <p style={{ whiteSpace: "pre-wrap" }}>{section.first_sentences.join(" ")}</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="button" disabled={blocked || previous.sentence_count <= steps || section.sentence_count === 0}
              onClick={() => void move(section.position, -steps)}>
              ↑ przenieś nagłówek wyżej {steps === 1 ? "o zdanie" : steps === 3 ? "o 3 zdania" : "o 5 zdań"}
            </button>
            <button type="button" className="button" disabled={blocked || section.sentence_count <= steps || previous.sentence_count === 0}
              onClick={() => void move(section.position, steps)}>
              ↓ przenieś nagłówek niżej {steps === 1 ? "o zdanie" : steps === 3 ? "o 3 zdania" : "o 5 zdań"}
            </button>
          </div>
        </section>;
      })}
    </details>
  );
}
