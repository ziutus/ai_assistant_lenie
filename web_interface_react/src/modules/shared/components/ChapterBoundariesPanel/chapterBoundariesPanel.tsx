import React from "react";
import axios from "axios";
import CollapsibleSection from "../CollapsibleSection/collapsibleSection";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";

import { EntityChips, type EntityItem } from "../EntitiesPanel/entitiesPanel";

type ChapterEntities = Record<string, EntityItem[]>;
interface EntityResponse { sections: { position: number; type: ChapterType; entities: ChapterEntities }[]; has_entities: boolean }

type ChapterType = "TEMAT" | "REKLAMA" | "SZUM" | "ZRODLA";
const typeLabels: Record<ChapterType, string> = { TEMAT: "Treść", REKLAMA: "Reklama", SZUM: "Szum", ZRODLA: "Źródła" };
const typeColors = { REKLAMA: "#fef3c7", SZUM: "#e5e7eb", ZRODLA: "#dbeafe" };

interface Section {
  type: ChapterType;
  note?: string;
  position: number;
  title: string;
  sentence_count: number;
  sentences: Sentence[];
}
interface Sentence { index: number; text: string }
interface ScrollAnchor { ordinal: number; top: number; chapterPosition?: number }
interface Props {
  docId: string;
  disabled?: boolean;
  defaultOpen?: boolean;
  onBusyChange?: (busy: boolean) => void;
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

export default function ChapterBoundariesPanel({ docId, disabled = false, defaultOpen = false, onBusyChange, onSaved }: Props) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const panel = React.useRef<HTMLDetailsElement>(null);
  const [pendingScrollRestore, setPendingScrollRestore] = React.useState<ScrollAnchor | null>(null);
  const [sections, setSections] = React.useState<Section[]>([]);
  const [entityData, setEntityData] = React.useState<EntityResponse | null>(null);
  const [entityError, setEntityError] = React.useState(false);
  const [typeChanged, setTypeChanged] = React.useState(false);
  const [openChapters, setOpenChapters] = React.useState<Set<number>>(new Set());
  const [isOpen, setIsOpen] = React.useState(defaultOpen);
  const [split, setSplit] = React.useState<{ position: number; index: number; title: string; chapterType: ChapterType } | null>(null);
  const splitTrigger = React.useRef<HTMLButtonElement | null>(null);
  const [busy, setBusy] = React.useState(false);
  const pending = React.useRef(false);
  const [error, setError] = React.useState("");
  const [hasEmbeddings, setHasEmbeddings] = React.useState(false);
  const [stale, setStale] = React.useState(false);
  const [typeConflict, setTypeConflict] = React.useState<{ kept: ChapterType; dropped: ChapterType } | null>(null);
  const headers = { "x-api-key": apiKey };
  const base = apiUrl + "/document/" + docId;
  const blocked = busy || disabled || hasEmbeddings;

  const chapters = sections.filter(section => section.position > 0);
  const chapterOffsets = new Map<number, number>();
  let sentenceTotal = 0;
  for (const chapter of chapters) {
    chapterOffsets.set(chapter.position, sentenceTotal);
    sentenceTotal += chapter.sentence_count;
  }

  React.useLayoutEffect(() => {
    if (!pendingScrollRestore) return;
    let row = pendingScrollRestore.chapterPosition
      ? panel.current?.querySelector<HTMLElement>('[data-chapter-position="' + pendingScrollRestore.chapterPosition + '"]')
      : panel.current?.querySelector<HTMLElement>('[data-gsi="' + pendingScrollRestore.ordinal + '"]');
    const chapter = row?.closest<HTMLDetailsElement>("details[data-chapter-position]");
    if (chapter && !chapter.open) row = chapter;
    if (row) {
      // Layout's content is in normal document flow; only the sidebar scrolls independently.
      window.scrollBy(0, row.getBoundingClientRect().top - pendingScrollRestore.top);
    }
    setPendingScrollRestore(null);
  }, [pendingScrollRestore]);

  const withLock = async (action: () => Promise<void>) => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    try { await action(); }
    catch (error) { setError(errorMessage(error)); }
    finally { pending.current = false; setBusy(false); onBusyChange?.(false); }
  };
  const loadSections = async (expandAll: boolean, reveal: number[] = [], scrollAnchor: ScrollAnchor | null = null, typeChange?: { position: number; type: string }) => {
    const [sectionResponse, entities] = await Promise.all([
      axios.get<{ sections: Section[]; has_embeddings: boolean }>(base + "/chapter_sections", {
        headers, params: { with_sentences: 1 },
      }),
      axios.get<EntityResponse>(base + "/chapter_entities", { headers }).then(response => response.data).catch(() => null),
    ]);
    const { data } = sectionResponse;
    setEntityData(entities);
    setEntityError(entities === null);
    setSections(data.sections);
    setHasEmbeddings(data.has_embeddings);
    setSplit(null);
    setOpenChapters(current => new Set(data.sections.filter(section => section.position > 0).filter(section => {
      const { position } = section;
      if (typeChange?.position === position) return typeChange.type === "TEMAT";
      if (reveal.includes(position)) return true;
      return expandAll ? !section.type || section.type === "TEMAT" : current.has(position);
    }).map(section => section.position)));
    // Schedule restoration only together with the fresh rows, never during intermediate busy renders.
    setPendingScrollRestore(scrollAnchor);
  };
  const load = () => withLock(() => loadSections(true));
  React.useEffect(() => {
    if (isOpen) void load();
  }, [isOpen, docId, apiUrl, apiKey]);
  const edit = (operation: string, payload: Record<string, string | number>) => {
    if (disabled || hasEmbeddings) return;
    return withLock(async () => {
      const position = Number(payload.position);
      const moving = operation === "move_chapter_boundary";
      const changingType = operation === "chapter_type";
      const count = Number(payload.sentences);
      const anchorPosition = moving && count < 0 ? position - 1 : position;
      const anchorChapter = chapters.find(chapter => chapter.position === anchorPosition);
      const anchorIndex = moving
        ? count > 0 ? count + 1 : (anchorChapter?.sentence_count ?? 0) + count + 1
        : operation === "split_chapter" ? Number(payload.sentence_index) : 1;
      const ordinal = (chapterOffsets.get(anchorPosition) ?? 0) + anchorIndex;
      // Native details keeps hidden sentence rows mounted; anchor closed chapters to their header.
      let anchorElement = (changingType
        ? panel.current?.querySelector<HTMLElement>('[data-chapter-position="' + position + '"]')
        : panel.current?.querySelector<HTMLElement>('[data-gsi="' + ordinal + '"]'))
        ?? panel.current?.querySelector<HTMLElement>('[data-chapter-position="' + anchorPosition + '"]');
      const anchorDetails = anchorElement?.closest<HTMLDetailsElement>("details[data-chapter-position]");
      if (anchorDetails && !anchorDetails.open) anchorElement = anchorDetails;
      const scrollAnchor = anchorElement ? { ordinal, top: anchorElement.getBoundingClientRect().top,
        ...(changingType ? { chapterPosition: position } : {}) } : null;
      const { data } = await axios.post(base + "/" + operation, payload, { headers });
      if (changingType) setTypeChanged(true);
      if (data.stale_analysis_runs > 0) setStale(true);
      if (data.type_conflict) setTypeConflict(data.type_conflict);
      setSplit(null);
      await onSaved();
      await loadSections(!moving && !changingType, moving ? [position - 1, position] : [], scrollAnchor,
        changingType ? { position, type: String(payload.type) } : undefined);
    });
  };
  const cancelSplit = () => { setSplit(null); splitTrigger.current?.focus(); };
  const submitSplit = () => {
    if (split && split.title.trim()) void edit("split_chapter", {
      position: split.position, sentence_index: split.index, title: split.title, chapter_type: split.chapterType,
    });
  };
  return (
    <CollapsibleSection title="Granice rozdziałów" ref={panel} open={isOpen} style={{ marginBottom: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}
      onToggle={event => { if (event.target === event.currentTarget) setIsOpen(event.currentTarget.open); }}>
      <p><NavLink to={"/ner/" + docId}>Przejrzyj NER per rozdział →</NavLink></p>
      <p>Zapisuje od razu w bazie. Po zmianie formularz zostanie odświeżony — wcześniej zapisz inne zmiany.</p>
      {hasEmbeddings && <p role="status">Dokument ma embeddingi — otwórz go ponownie do edycji przed zmianą granic rozdziałów.</p>}
      {stale && <p role="status" style={{ color: "#92400e" }}>
        Rozdziały w czytniku zostały zaktualizowane. Istniejące chunki (<NavLink to={"/chunks/" + docId}>{"/chunks/" + docId}</NavLink>) powstały ze starego podziału — uruchom analizę ponownie.
      </p>}
      {typeConflict && <p role="alert" style={{ color: "#92400e" }}>
        Scalono rozdziały o różnych typach — zachowano typ: {typeLabels[typeConflict.kept]}, pominięto: {typeLabels[typeConflict.dropped]}
      </p>}
      {typeChanged && <p role="status" style={{ color: "#92400e" }}>Zmieniono typ rozdziału — odśwież encje przyciskiem „Wykryj osoby, miejsca i obiekty”.</p>}
      {entityError && <small>Nie udało się pobrać encji</small>}
      {error && <p role="alert">{error} <button type="button" onClick={load} disabled={busy}>Odśwież</button></p>}
      <p role="status" style={{ minHeight: "1.5em" }}>{busy ? "Przetwarzam…" : ""}</p>
      {chapters.map(section => {
        const isOpen = openChapters.has(section.position);
        const entities = entityData?.sections.find(item => item.position === section.position)?.entities;
        const skipped = section.type && section.type !== "TEMAT";
        const entityCount = skipped ? 0 : Object.values(entities ?? {}).reduce((count, items) => count + items.length, 0);
        return <CollapsibleSection key={section.position} role="region" open={isOpen}
          onToggle={event => {
            const opened = event.currentTarget.open;
            setOpenChapters(current => { const next = new Set(current); if (opened) next.add(section.position); else next.delete(section.position); return next; });
            if (!opened && split?.position === section.position) setSplit(null);
          }}
          title={<strong>#{section.position} {section.title} · {section.sentence_count} zdań</strong>}
          summaryExtra={section.type && section.type !== "TEMAT" && <span aria-label={"Typ: " + typeLabels[section.type]}
            style={{ background: typeColors[section.type], color: "#334155", borderRadius: 4, padding: "2px 6px" }}>{typeLabels[section.type]}</span>} data-chapter-position={section.position} aria-label={"Rozdział " + section.position + ": " + section.title}
          style={{ marginTop: 12, padding: 10, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select aria-label={"Typ rozdziału " + section.position} value={section.type || "TEMAT"} disabled={blocked}
              onChange={event => void edit("chapter_type", { position: section.position, type: event.target.value })}>
              {Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {section.position >= 2 && <button type="button" style={cardButtonStyle} disabled={blocked}
              aria-label={"Scal rozdział " + section.position + " z poprzednim"}
              onClick={() => {
                if (window.confirm("Scalić ten rozdział z poprzednim? Numery kolejnych rozdziałów w czytniku zmienią się.")) {
                  void edit("merge_chapter", { position: section.position });
                }
              }}>⇡ Scal z poprzednim</button>}
            {section.position < chapters.length && <button type="button" style={cardButtonStyle} disabled={blocked}
              aria-label={"Scal rozdział " + section.position + " z następnym"}
              onClick={() => {
                if (window.confirm("Scalić ten rozdział z następnym? Numery kolejnych rozdziałów w czytniku zmienią się.")) {
                  void edit("merge_chapter", { position: section.position + 1 });
                }
              }}>⇣ Scal z następnym</button>}
          </div>
          <details>
            <summary style={{ cursor: "pointer", fontSize: "0.85em" }}>Encje ({entityCount})</summary>
            {skipped ? <p>Rozdział pominięty w NER (typ: {typeLabels[section.type]})</p>
              : entityData?.has_entities === false ? <p>Brak zapisanych encji — użyj „Wykryj osoby, miejsca i obiekty” poniżej.</p>
              : entities && <>
                <EntityChips label="Osoby" items={entities.persName ?? []} />
                <EntityChips label="Miejsca" items={[...(entities.geogName ?? []), ...(entities.placeName ?? [])]} />
                <EntityChips label="Organizacje" items={entities.orgName ?? []} />
              </>}
          </details>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
          <div id={"chapter-sentences-" + docId + "-" + section.position} style={{ marginTop: 10, flex: "1 1 320px", minWidth: 0 }}>
            {section.sentences?.map(sentence => {
              const marked = split?.position === section.position && split.index === sentence.index;
              const label = " — rozdział " + section.position + ", zdanie " + sentence.index;
              return <div key={sentence.index} data-gsi={(chapterOffsets.get(section.position) ?? 0) + sentence.index} aria-label={"Zdanie " + sentence.index}
                style={{ position: "relative", paddingLeft: 82, marginBottom: 8, borderRadius: 2, minHeight: "1.4em",
                  ...(marked ? { background: "#fff7ed", borderLeft: "3px solid #f97316" } : {}) }}>
                <span style={{ position: "absolute", left: 0, top: 1, display: "flex", gap: 3 }}>
                  {sentence.index > 1 && <SentenceButton symbol="✂" title="Podziel tutaj — to zdanie zacznie nowy rozdział"
                    label={"Podziel tutaj" + label} disabled={blocked} onClick={event => {
                      splitTrigger.current = event.currentTarget;
                      setSplit({ position: section.position, index: sentence.index, title: (section.title + " (cd.)").slice(0, 200), chapterType: section.type || "TEMAT" });
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
                  <label>Typ nowego rozdziału <select value={split.chapterType} disabled={blocked}
                    onChange={event => setSplit({ ...split, chapterType: event.target.value as ChapterType })}>
                    {Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select></label>
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <button type="button" style={cardButtonStyle} disabled={blocked || !split.title.trim()} onClick={submitSplit}>Podziel</button>
                    <button type="button" style={cardButtonStyle} disabled={busy} onClick={cancelSplit}>Anuluj</button>
                  </div>
                </div>}
              </div>;
            })}
            {section.sentences?.length === 0 && <em style={{ color: "#94a3b8" }}>Brak zdań.</em>}
          </div>
          <ChapterNote key={docId + ":" + section.position + ":" + (section.note ?? "")} note={section.note ?? ""}
            position={section.position} disabled={blocked} onSave={note => withLock(async () => {
              if (disabled || hasEmbeddings) return;
              await axios.post(base + "/chapter_note", { position: section.position, note }, { headers });
              setSections(current => current.map(item => item.position === section.position ? { ...item, note } : item));
            })} />
          </div>
        </CollapsibleSection>;
      })}
    </CollapsibleSection>
  );
}

function ChapterNote({ note, position, disabled, onSave }: {
  note: string; position: number; disabled: boolean; onSave: (note: string) => Promise<void>;
}) {
  const [draft, setDraft] = React.useState(note);
  const dirty = draft !== note;
  return <div style={{ flex: "0 1 260px", maxWidth: "100%", marginTop: 10 }}>
    <label>Notatka dla LLM
      <textarea aria-label={"Notatka dla LLM — rozdział " + position} maxLength={2000} rows={6}
        style={{ width: "100%", boxSizing: "border-box" }} value={draft} disabled={disabled}
        onChange={event => setDraft(event.target.value)} />
    </label>
    {dirty && <small>Niezapisane zmiany</small>}
    <button type="button" style={cardButtonStyle} disabled={disabled || !dirty || draft.length > 2000}
      onClick={() => void onSave(draft)}>Zapisz notatkę</button>
  </div>;
}
