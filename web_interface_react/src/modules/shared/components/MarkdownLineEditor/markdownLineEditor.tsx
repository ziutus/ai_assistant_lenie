import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";

type MarkKind = "author" | "date" | "sources" | "links" | "ads" | "persons";

const emptyMarks = (): Record<MarkKind, Set<number>> => ({
  author: new Set(), date: new Set(), sources: new Set(), links: new Set(), ads: new Set(), persons: new Set(),
});

const MarkdownLineEditor = ({ formik, disabled }: { formik: any; disabled: boolean }) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const value: string = formik.values.text_md || formik.values.text || "";
  const lines: string[] = value.split("\n");
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
      </div>
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
          <div style={{ border: "1px solid #e2e8f0", borderRadius: 5, maxHeight: "68vh", overflow: "auto" }}>
            {lines.map((line, index) => (
              <div key={`${index}-${line.slice(0, 30)}`} style={{
                display: "grid", gridTemplateColumns: compactLabels ? "46px repeat(9, 34px) minmax(280px, 1fr)" : "46px repeat(9, auto) minmax(280px, 1fr)", gap: 5,
                alignItems: "start", padding: "3px 6px", borderBottom: "1px solid #f1f5f9",
                background: marked("persons", index) ? "#fef3c7" : marked("author", index) ? "#f3e8ff" : marked("date", index) ? "#dbeafe" : marked("sources", index) ? "#ede9fe" : marked("links", index) ? "#dcfce7" : marked("ads", index) ? "#fee2e2" : index % 2 ? "#fafafa" : "white",
              }}>
                <span style={{ color: "#94a3b8", textAlign: "right", paddingTop: 3 }}>{index + 1}</span>
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
            ))}
          </div>
        </>
      )}
    </section>
  );
};

export default MarkdownLineEditor;
