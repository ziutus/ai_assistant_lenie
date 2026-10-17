import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";

interface Section {
  position: number;
  title: string;
  sentence_count: number;
}
interface Sentence { index: number; text: string }
interface Props {
  docId: string;
  disabled?: boolean;
  onSaved: () => Promise<unknown>;
}
const lineButtonStyle: React.CSSProperties = {
  background: "none", border: "1px solid #e2e8f0", borderRadius: 3,
  fontSize: "0.78em", cursor: "pointer", padding: "0 4px", lineHeight: "1.3em", color: "#94a3b8",
};
const cardButtonStyle: React.CSSProperties = {
  padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 4,
  background: "#fff", cursor: "pointer", fontSize: "0.82em", color: "#64748b",
};
function SentenceButton({ symbol, title, label, disabled, onClick }: {
  symbol: string; title: string; label: string; disabled: boolean;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  return <button type="button" title={title} aria-label={label} disabled={disabled} onClick={onClick}
    style={lineButtonStyle}
    onMouseEnter={event => { if (!disabled) { event.currentTarget.style.background = "#fef3c7"; event.currentTarget.style.color = "#92400e"; } }}
    onMouseLeave={event => { event.currentTarget.style.background = "none"; event.currentTarget.style.color = "#94a3b8"; }}>
    {symbol}
  </button>;
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
  const [expanded, setExpanded] = React.useState<Set<number>>(new Set());
  const [sentences, setSentences] = React.useState<Record<number, Sentence[]>>({});
  const [split, setSplit] = React.useState<{ position: number; index: number; title: string } | null>(null);
  const splitTrigger = React.useRef<HTMLButtonElement | null>(null);
  const [busy, setBusy] = React.useState(false);
  const pending = React.useRef(false);
  const [error, setError] = React.useState("");
  const [hasEmbeddings, setHasEmbeddings] = React.useState(false);
  const [stale, setStale] = React.useState(false);
  const headers = { "x-api-key": apiKey };
  const base = apiUrl + "/document/" + docId;
  const blocked = busy || disabled || hasEmbeddings;

  const withLock = async (action: () => Promise<void>) => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try { await action(); }
    catch (error) { setError(errorMessage(error)); }
    finally { pending.current = false; setBusy(false); }
  };
  const getSentences = async (position: number): Promise<Sentence[]> => {
    const { data } = await axios.get(base + "/chapter_sections/" + position + "/sentences", { headers });
    return data.sentences;
  };
  const reloadExpanded = async (positions: number[]) => {
    const entries = await Promise.all(positions.map(async position => [position, await getSentences(position)] as const));
    setSentences(Object.fromEntries(entries));
  };
  const load = () => withLock(async () => {
    const { data } = await axios.get(base + "/chapter_sections", { headers });
    setSections(data.sections);
    setHasEmbeddings(data.has_embeddings);
    setSentences({});
    setSplit(null);
    await reloadExpanded([...expanded].filter(position => data.sections.some((section: Section) => section.position === position)));
  });
  const toggleChapter = (position: number) => {
    if (pending.current) return;
    if (expanded.has(position)) {
      setExpanded(current => { const next = new Set(current); next.delete(position); return next; });
      if (split?.position === position) setSplit(null);
      return;
    }
    setExpanded(current => new Set([...current, position]));
    if (!sentences[position]) void withLock(async () => {
      const rows = await getSentences(position);
      setSentences(current => ({ ...current, [position]: rows }));
    });
  };
  const edit = (operation: string, payload: Record<string, string | number>) => {
    if (disabled || hasEmbeddings) return;
    return withLock(async () => {
      const { data } = await axios.post(base + "/" + operation, payload, { headers });
      setSections(data.sections);
      setHasEmbeddings(data.has_embeddings);
      if (data.stale_analysis_runs > 0) setStale(true);
      setSplit(null);
      setSentences({});
      if (operation !== "move_chapter_boundary") setExpanded(new Set());
      await onSaved();
      if (operation === "move_chapter_boundary") await reloadExpanded([...expanded]);
    });
  };
  const cancelSplit = () => { setSplit(null); splitTrigger.current?.focus(); };
  const submitSplit = () => {
    if (split && split.title.trim()) void edit("split_chapter", {
      position: split.position, sentence_index: split.index, title: split.title,
    });
  };
  const chapters = sections.filter(section => section.position > 0);

  return (
    <details style={{ marginBottom: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}
      onToggle={event => { if (event.currentTarget.open) void load(); }}>
      <summary style={{ cursor: "pointer", fontWeight: "bold" }}>Granice rozdziałów</summary>
      <p>Zapisuje od razu w bazie. Po zmianie formularz zostanie odświeżony — wcześniej zapisz inne zmiany.</p>
      {hasEmbeddings && <p role="status">Dokument ma embeddingi — otwórz go ponownie do edycji przed zmianą granic rozdziałów.</p>}
      {stale && <p role="status" style={{ color: "#92400e" }}>
        Rozdziały w czytniku zostały zaktualizowane. Istniejące chunki (<NavLink to={"/chunks/" + docId}>{"/chunks/" + docId}</NavLink>) powstały ze starego podziału — uruchom analizę ponownie.
      </p>}
      {error && <p role="alert">{error} <button type="button" onClick={load} disabled={busy}>Odśwież</button></p>}
      {busy && <p role="status">Przetwarzam…</p>}
      {chapters.map(section => {
        const isOpen = expanded.has(section.position);
        return <section key={section.position} aria-label={"Rozdział " + section.position + ": " + section.title}
          style={{ marginTop: 12, padding: 10, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <strong>#{section.position} {section.title} · {section.sentence_count} zdań</strong>
            <button type="button" aria-expanded={isOpen} aria-controls={"chapter-sentences-" + docId + "-" + section.position}
              aria-label={(isOpen ? "Zwiń" : "Rozwiń") + " rozdział " + section.position}
              style={cardButtonStyle} disabled={busy} onClick={() => toggleChapter(section.position)}>
              {isOpen ? "▾ Zwiń" : "▸ Rozwiń"}
            </button>
            {section.position >= 2 && <button type="button" style={cardButtonStyle} disabled={blocked}
              aria-label={"Scal rozdział " + section.position + " z poprzednim"}
              onClick={() => {
                if (window.confirm("Scalić ten rozdział z poprzednim? Numery kolejnych rozdziałów w czytniku zmienią się.")) {
                  void edit("merge_chapter", { position: section.position });
                }
              }}>⇡ Scal z poprzednim</button>}
          </div>
          {isOpen && <div id={"chapter-sentences-" + docId + "-" + section.position} style={{ marginTop: 10 }}>
            {sentences[section.position]?.map(sentence => {
              const marked = split?.position === section.position && split.index === sentence.index;
              const label = " — rozdział " + section.position + ", zdanie " + sentence.index;
              return <div key={sentence.index} aria-label={"Zdanie " + sentence.index}
                style={{ position: "relative", paddingLeft: 82, marginBottom: 8, borderRadius: 2, minHeight: "1.4em",
                  ...(marked ? { background: "#fff7ed", borderLeft: "3px solid #f97316" } : {}) }}>
                <span style={{ position: "absolute", left: 0, top: 1, display: "flex", gap: 3 }}>
                  {sentence.index > 1 && <SentenceButton symbol="✂" title="Podziel tutaj — to zdanie zacznie nowy rozdział"
                    label={"Podziel tutaj" + label} disabled={blocked} onClick={event => {
                      splitTrigger.current = event.currentTarget;
                      setSplit({ position: section.position, index: sentence.index, title: (section.title + " (cd.)").slice(0, 200) });
                    }} />}
                  {section.position >= 2 && sentence.index < section.sentence_count && <SentenceButton symbol="↑"
                    title="Przenieś to zdanie i wcześniejsze do poprzedniego rozdziału" label={"Przenieś do poprzedniego" + label}
                    disabled={blocked || sections.find(item => item.position === section.position - 1)?.sentence_count === 0}
                    onClick={() => void edit("move_chapter_boundary", { position: section.position, sentences: sentence.index })} />}
                  {section.position < chapters.length && sentence.index > 1 && <SentenceButton symbol="↓"
                    title="Przenieś to zdanie i następne do następnego rozdziału" label={"Przenieś do następnego" + label}
                    disabled={blocked || sections.find(item => item.position === section.position + 1)?.sentence_count === 0}
                    onClick={() => void edit("move_chapter_boundary", {
                      position: section.position + 1, sentences: -(section.sentence_count - sentence.index + 1),
                    })} />}
                </span>
                <span style={{ whiteSpace: "pre-wrap", fontSize: "0.88em", lineHeight: 1.6 }}>{sentence.text}</span>
                {marked && split && <div role="group" aria-label="Podział rozdziału" style={{ marginTop: 6 }}
                  onKeyDown={event => {
                    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); if (!busy) cancelSplit(); }
                    if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
                      event.preventDefault(); event.stopPropagation(); if (!blocked) submitSplit();
                    }
                  }}>
                  <label>Tytuł nowego rozdziału <input autoFocus maxLength={200} value={split.title} disabled={blocked}
                    onChange={event => setSplit({ ...split, title: event.target.value })} /></label>
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <button type="button" style={cardButtonStyle} disabled={blocked || !split.title.trim()} onClick={submitSplit}>Podziel</button>
                    <button type="button" style={cardButtonStyle} disabled={busy} onClick={cancelSplit}>Anuluj</button>
                  </div>
                </div>}
              </div>;
            })}
            {sentences[section.position]?.length === 0 && <em style={{ color: "#94a3b8" }}>Brak zdań.</em>}
          </div>}
        </section>;
      })}
    </details>
  );
}
