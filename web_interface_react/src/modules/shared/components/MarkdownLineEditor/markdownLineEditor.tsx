import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";
import { canMergeChunkRanges, chunkLocalSplitLines, computeChunkLineRanges, type ChunkForPreview } from "../../utils/chunkBoundaries";

const chunkColor = (type: string) => ({
  TEMAT: "#22c55e", REKLAMA: "#f97316", SZUM: "#94a3b8", ZRODLA: "#3b82f6",
}[type] ?? "#64748b");

type MarkKind = "author" | "date" | "sources" | "links" | "ads" | "persons";

const emptyMarks = (): Record<MarkKind, Set<number>> => ({
  author: new Set(), date: new Set(), sources: new Set(), links: new Set(), ads: new Set(), persons: new Set(),
});

const MarkdownLineEditor = ({ formik, disabled, chunks, chunksStale, onRequestChunks, onRefreshChunks, onChangeChunkType, onMergeChunk, onSplitChunk }: {
  formik: any; disabled: boolean; chunks?: ChunkForPreview[]; onRequestChunks?: () => Promise<void>;
  chunksStale?: boolean;
  onRefreshChunks?: () => Promise<void>;
  onChangeChunkType?: (id: number, type: string) => Promise<void>;
  onMergeChunk?: (id: number) => Promise<void>;
  onSplitChunk?: (id: number, splitAtLines: number[]) => Promise<void>;
}) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const value: string = formik.values.text_md || formik.values.text || "";
  const lines = React.useMemo(() => value.split("\n"), [value]);
  const ranges = React.useMemo(() => computeChunkLineRanges(lines, chunks ?? []), [lines, chunks]);
  const [showChunkPreview, setShowChunkPreview] = React.useState(false);
  const [loadingChunks, setLoadingChunks] = React.useState(false);
  const [chunkError, setChunkError] = React.useState("");
  const [pendingSplits, setPendingSplits] = React.useState<Record<number, Set<number>>>({});
  const [mutatingChunk, setMutatingChunk] = React.useState(false);
  const mutationInFlight = React.useRef(false);
  // Global line selections become obsolete whenever the document text changes.
  React.useEffect(() => { setPendingSplits({}); }, [value]);
  const mutateChunk = async (action: () => Promise<void>) => {
    if (!showChunkPreview || disabled || mutationInFlight.current) return;
    if (chunksStale && !window.confirm("Tekst dokumentu zmienił się od ostatniego wczytania chunków. Ta akcja użyje zapisanej wcześniej treści chunka, nie najnowszych zmian w tekście na ekranie. Kontynuować?")) return;
    mutationInFlight.current = true;
    setMutatingChunk(true);
    setChunkError("");
    let saved = false;
    try {
      await action();
      saved = true;
      setPendingSplits({});
      await onRefreshChunks?.();
    } catch {
      setChunkError(saved
        ? "Zapisano zmianę, ale nie udało się odświeżyć chunków. Wyłącz i włącz podgląd, aby ponowić pobieranie."
        : "Nie udało się zmienić chunka. Spróbuj ponownie.");
    } finally {
      mutationInFlight.current = false;
      setMutatingChunk(false);
    }
  };
  const toggleSplit = (id: number, line: number) => setPendingSplits(previous => {
    const points = new Set(previous[id]);
    if (points.has(line)) points.delete(line);
    else points.add(line);
    return { ...previous, [id]: points };
  });
  const toggleChunkPreview = async () => {
    if (loadingChunks || mutationInFlight.current) return;
    setChunkError("");
    if (!showChunkPreview && onRequestChunks) {
      setLoadingChunks(true);
      try { await onRequestChunks(); }
      catch { setChunkError("Nie udało się pobrać chunków. Spróbuj ponownie."); return; }
      finally { setLoadingChunks(false); }
    }
    setShowChunkPreview(current => !current);
  };
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(value);
  const [marks, setMarks] = React.useState<Record<MarkKind, Set<number>>>(emptyMarks);
  const [compactLabels, setCompactLabels] = React.useState(true);
  const [busy, setBusy] = React.useState<MarkKind | null>(null);
  const [message, setMessage] = React.useState("");

  React.useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);

  const changeText = (next: string) => {
    formik.setFieldValue("text_md", next);
    setMarks(emptyMarks());
  };
  const removeLine = (index: number) => changeText(lines.filter((_, i) => i !== index).join("\n"));
  const keepFrom = (index: number) => {
    if (index === 0 || window.confirm(`Usunąć ${index} linii przed wybraną linią?`)) changeText(lines.slice(index).join("\n"));
  };
  const keepThrough = (index: number) => {
    const removed = lines.length - index - 1;
    if (removed === 0 || window.confirm(`Usunąć ${removed} linii po wybranej linii?`)) changeText(lines.slice(0, index + 1).join("\n"));
  };
  // First click sets a section anchor; second click fills the entire
  // contiguous range. A third click starts a new range for that category.
  const toggleMark = (kind: MarkKind, index: number) => setMarks(prev => {
    const current = prev[kind];
    let next: Set<number>;
    if (current.size === 0) next = new Set([index]);
    else if (current.size === 1 && !current.has(index)) {
      const anchor = [...current][0];
      next = new Set(Array.from({ length: Math.abs(index - anchor) + 1 }, (_, offset) => Math.min(anchor, index) + offset));
    } else next = new Set([index]);
    return { ...prev, [kind]: next };
  });
  const selectedText = (kind: MarkKind) => [...marks[kind]].sort((a, b) => a - b).map(i => lines[i]).join("\n").trim();
  const headers = { "x-api-key": `${apiKey ?? ""}`, "Content-Type": "application/json" };

  const saveAuthorSection = async () => {
    const text = selectedText("author");
    if (!text) return;
    setBusy("author"); setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/document/${formik.values.id}/extract_author`, {
        context_text: text, biography_text: text,
      }, { headers });
      if (response.data.byline) {
        formik.setFieldValue("byline", response.data.byline);
        setMessage(`Zapisano autora: ${response.data.byline}${response.data.biography ? " oraz notkę biograficzną" : ""}.`);
      } else setMessage("Nie rozpoznano autora w zaznaczonej sekcji.");
    } catch { setMessage("Nie udało się zapisać autora i biografii."); }
    finally { setBusy(null); }
  };

  const saveDateLine = async () => {
    const text = selectedText("date");
    if (!text) return;
    setBusy("date"); setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/document/${formik.values.id}/extract_publication_date`, {
        context_text: text,
      }, { headers });
      if (response.data.published_on) {
        formik.setFieldValue("published_on", response.data.published_on);
        formik.setFieldValue("published_on_method", response.data.published_on_method || "llm");
        setMessage(`Zapisano datę publikacji: ${response.data.published_on}.`);
      } else setMessage("Nie rozpoznano daty w zaznaczonych liniach.");
    } catch { setMessage("Nie udało się zapisać daty publikacji."); }
    finally { setBusy(null); }
  };

  const savePersonsSection = async () => {
    const text = selectedText("persons");
    if (!text) return;
    setBusy("persons"); setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/document/${formik.values.id}/extract_persons`, {
        context_text: text,
      }, { headers });
      const found: string[] = response.data.persons_found || [];
      const linked = response.data.linked || [];
      if (found.length) setMessage(`Rozpoznano: ${found.join(", ")}. Dodano ${linked.length} nowych powiązań z dokumentem.`);
      else setMessage("Nie rozpoznano osób w zaznaczonej sekcji.");
    } catch { setMessage("Nie udało się pobrać osób z zaznaczonej sekcji."); }
    finally { setBusy(null); }
  };

  const markSourcesSection = () => {
    const selected = [...marks.sources].sort((a, b) => a - b);
    if (!selected.length) return;
    const first = selected[0];
    if (first > 0 && /^#{1,6}\s+źr[oó]d/i.test(lines[first - 1].trim())) {
      setMessage("Ta sekcja ma już nagłówek Źródła.");
      return;
    }
    changeText([...lines.slice(0, first), "## Źródła", ...lines.slice(first)].join("\n"));
    setMessage("Dodano nagłówek „## Źródła”. Zapisz dokument głównym przyciskiem.");
  };

  const addSectionHeading = (kind: "sources" | "links", heading: string) => {
    const selected = [...marks[kind]].sort((a, b) => a - b);
    if (!selected.length) return;
    const first = selected[0];
    if (first > 0 && lines[first - 1].trim().toLocaleLowerCase("pl").includes(heading.toLocaleLowerCase("pl"))) {
      setMessage(`Ta sekcja ma już nagłówek ${heading}.`); return;
    }
    changeText([...lines.slice(0, first), `## ${heading}`, ...lines.slice(first)].join("\n"));
    setMessage(`Dodano nagłówek „## ${heading}”. Zapisz dokument głównym przyciskiem.`);
  };

  const deleteMarkedSections = () => {
    const selected = new Set<number>();
    (Object.keys(marks) as MarkKind[]).forEach(kind => marks[kind].forEach(index => selected.add(index)));
    if (!selected.size || !window.confirm(`Usunąć ${selected.size} zaznaczonych linii ze wszystkich sekcji?`)) return;
    changeText(lines.filter((_, index) => !selected.has(index)).join("\n"));
    setMessage(`Usunięto ${selected.size} linii z zaznaczonych sekcji.`);
  };

  const marked = (kind: MarkKind, index: number) => marks[kind].has(index);
  const label = (shortLabel: string, fullLabel: string) => compactLabels ? shortLabel : fullLabel;
  return (
    <section style={{ margin: "8px 0 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 7 }}>
        <strong>Treść artykułu — recenzja linii ({lines.length})</strong>
        <button type="button" className="button" onClick={() => { setDraft(value); setEditing(v => !v); }}>
          {editing ? "Wróć do linii" : "Edytuj cały Markdown"}
        </button>
        <button type="button" className="button" onClick={() => setCompactLabels(current => !current)}>
          {compactLabels ? "Pełne nazwy przycisków" : "Skróty przycisków"}
        </button>
        {(chunks !== undefined || !!onRequestChunks || showChunkPreview) && (
          <span role="button" tabIndex={0} className="button" aria-disabled={loadingChunks || mutatingChunk}
            aria-pressed={showChunkPreview} onClick={toggleChunkPreview}
            onKeyDown={event => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                void toggleChunkPreview();
              }
            }}>
            {loadingChunks ? "Pobieram chunki…" : showChunkPreview ? "Skryj podział na chunki" : "Pokaż podział na chunki"}
          </span>
        )}
      </div>
      {chunkError && <div role="alert" style={{ marginBottom: 8 }}>{chunkError}</div>}
      {editing ? (
        <div>
          <textarea value={draft} disabled={disabled} onChange={e => setDraft(e.target.value)}
            style={{ width: "100%", minHeight: 560, boxSizing: "border-box", padding: 10, fontFamily: "monospace", lineHeight: 1.5 }} />
          <button type="button" className="button" disabled={disabled || !draft.trim()} onClick={() => { changeText(draft); setEditing(false); }}>
            Zastosuj edycję w formularzu
          </button>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8, padding: 8, background: "#f8fafc" }}>
            <button type="button" className="button" disabled={!marks.author.size || !!busy} onClick={saveAuthorSection}>
              {busy === "author" ? "Analizuję…" : `Zapisz autora + biografię (${marks.author.size})`}
            </button>
            <button type="button" className="button" disabled={!marks.date.size || !!busy} onClick={saveDateLine}>
              {busy === "date" ? "Analizuję…" : `Zapisz datę (${marks.date.size})`}
            </button>
            <button type="button" className="button" disabled={!marks.persons.size || !!busy} onClick={savePersonsSection}>
              {busy === "persons" ? "Analizuję…" : label(`P (${marks.persons.size})`, `Dodaj osoby (${marks.persons.size})`)}
            </button>
            <button type="button" className="button" disabled={!marks.sources.size || !!busy} onClick={markSourcesSection}>
              Oznacz sekcję Źródła ({marks.sources.size})
            </button>
            <button type="button" className="button" disabled={!marks.links.size || !!busy} onClick={() => addSectionHeading("links", "Linki")}>
              Oznacz sekcję Linki ({marks.links.size})
            </button>
            <button type="button" className="button" disabled={!Object.values(marks).some(set => set.size) || !!busy} onClick={deleteMarkedSections}>
              Usuń zaznaczone sekcje
            </button>
            <button type="button" onClick={() => setMarks(emptyMarks())}>{label("0", "Wyczyść zaznaczenia")}</button>
          </div>
          {message && <div style={{ marginBottom: 8 }}>{message}</div>}
          {showChunkPreview && !!chunks?.length && ranges.length < chunks.length && (
            <div style={{ marginBottom: 8, fontSize: "0.85em", color: "#64748b" }}>
              {chunks.length - ranges.length} z {chunks.length} chunków nie udało się dopasować do aktualnego tekstu (tekst zmienił się od czasu analizy).
            </div>
          )}
          {showChunkPreview && chunks?.length === 0 && (
            <div style={{ marginBottom: 8, fontSize: "0.85em", color: "#64748b" }}>Brak chunków w tej analizie.</div>
          )}
          <div style={{ border: "1px solid #e2e8f0", borderRadius: 5, maxHeight: "68vh", overflow: "auto" }}>
            {lines.map((line, index) => {
              const range = showChunkPreview ? ranges.find(range => range.startLine <= index && index <= range.endLine) : undefined;
              const chunk = range && chunks ? chunks[range.chunkIndex] : undefined;
              const nextRange = range ? ranges[ranges.indexOf(range) + 1] : undefined;
              const splitPoints = chunk ? pendingSplits[chunk.id] : undefined;
              return (
              <React.Fragment key={`${index}-${line.slice(0, 30)}`}>
              <div style={{
                display: "grid", gridTemplateColumns: `${showChunkPreview && ranges.length ? "120px" : "46px"} repeat(9, ${compactLabels ? "34px" : "auto"}) minmax(280px, 1fr)`, gap: 5,
                alignItems: "start", padding: "3px 6px", borderBottom: "1px solid #f1f5f9",
                borderLeft: chunk ? `4px solid ${chunkColor(chunk.type)}` : undefined,
                borderTop: chunk && range && range.startLine === index ? `2px solid ${chunkColor(chunk.type)}` : undefined,
                background: marked("persons", index) ? "#fef3c7" : marked("author", index) ? "#f3e8ff" : marked("date", index) ? "#dbeafe" : marked("sources", index) ? "#ede9fe" : marked("links", index) ? "#dcfce7" : marked("ads", index) ? "#fee2e2" : index % 2 ? "#fafafa" : "white",
              }}>
                <span style={{ color: "#94a3b8", textAlign: "right", paddingTop: 3 }}>
                  {chunk && range && range.startLine === index && (
                    <>
                    <span title={`chunk #${range.chunkIndex + 1} — ${chunk.type} — ${chunk.status}`}
                      style={{ display: "inline-block", borderRadius: 8, padding: "1px 3px", fontSize: 10,
                        color: chunkColor(chunk.type), border: `1px solid ${chunkColor(chunk.type)}`, marginRight: 3 }}>
                      #{range.chunkIndex + 1} {chunk.type}
                    </span>
                    {onChangeChunkType && <button type="button" disabled={disabled || mutatingChunk}
                      onClick={() => void mutateChunk(() => onChangeChunkType(chunk.id, chunk.type === "TEMAT" ? "SZUM" : "TEMAT"))}>
                      {chunk.type === "TEMAT" ? "Wylacz z analizy" : "Wlacz jako TEMAT"}
                    </button>}
                    {!!splitPoints?.size && onSplitChunk && <>
                      <button type="button" disabled={disabled || mutatingChunk}
                        onClick={() => void mutateChunk(() => onSplitChunk(chunk.id, chunkLocalSplitLines(splitPoints, range)))}>
                        Zastosuj podzial ({splitPoints.size})
                      </button>
                      <button type="button" disabled={disabled || mutatingChunk}
                        onClick={() => setPendingSplits(previous => ({ ...previous, [chunk.id]: new Set<number>() }))}>
                        Anuluj
                      </button>
                    </>}
                    </>
                  )}
                  {index + 1}
                  {chunk && range && index > range.startLine && onSplitChunk && (
                    <button type="button" title="Podziel chunk przed tą linią"
                      aria-label={`Podziel chunk przed linią ${index + 1}`} aria-pressed={splitPoints?.has(index) ?? false}
                      disabled={disabled || mutatingChunk} onClick={() => toggleSplit(chunk.id, index)}
                      style={{ background: splitPoints?.has(index) ? "#bfdbfe" : undefined }}>
                      &#9986;
                    </button>
                  )}
                </span>
                <button type="button" title="Usuń linię" onClick={() => removeLine(index)}>{label("×", "Usuń")}</button>
                <button type="button" title="Usuń wszystko przed tą linią" onClick={() => keepFrom(index)}>{label("⇤", "Początek")}</button>
                <button type="button" title="Usuń wszystko po tej linii" onClick={() => keepThrough(index)}>{label("⇥", "Koniec")}</button>
                <button type="button" title="Autor lub notka biograficzna" onClick={() => toggleMark("author", index)} style={{ fontWeight: marked("author", index) ? 700 : 400 }}>{label("A", "Autor/bio")}</button>
                <button type="button" title="Data publikacji" onClick={() => toggleMark("date", index)} style={{ fontWeight: marked("date", index) ? 700 : 400 }}>{label("D", "Data")}</button>
                <button type="button" title="Element sekcji źródeł" onClick={() => toggleMark("sources", index)} style={{ fontWeight: marked("sources", index) ? 700 : 400 }}>{label("Ź", "Źródła")}</button>
                <button type="button" title="Pierwsze kliknięcie: początek sekcji linków; drugie: koniec" onClick={() => toggleMark("links", index)} style={{ fontWeight: marked("links", index) ? 700 : 400 }}>{label("L", "Linki")}</button>
                <button type="button" title="Pierwsze kliknięcie: początek reklamy/szumu; drugie: koniec" onClick={() => toggleMark("ads", index)} style={{ fontWeight: marked("ads", index) ? 700 : 400 }}>{label("R", "Reklama")}</button>
                <button type="button" title="Pierwsze kliknięcie: początek sekcji osób; drugie: koniec" onClick={() => toggleMark("persons", index)} style={{ fontWeight: marked("persons", index) ? 700 : 400 }}>{label("P", "Osoby")}</button>
                <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", paddingTop: 3 }}>
                  {line || <em style={{ color: "#cbd5e1" }}>pusta linia</em>}
                </span>
              </div>
              {chunk && range && index === range.endLine && onMergeChunk && canMergeChunkRanges(range, nextRange, chunks ?? []) && (
                <div style={{ padding: "3px 6px" }}>
                  <button type="button" disabled={disabled || mutatingChunk}
                    onClick={() => void mutateChunk(() => onMergeChunk(chunk.id))}>
                    &#128279; Scal z nastepnym
                  </button>
                </div>
              )}
              </React.Fragment>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
};

export default MarkdownLineEditor;
