import React from "react";
import axios from "axios";
import { Link, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import EntitiesPanel, { type EntitiesByType, type EntityItem } from "../components/EntitiesPanel/entitiesPanel";
import { splitByEntities, type HighlightEntry, type HighlightKind } from "../utils/entityHighlight";

type ChapterType = "TEMAT" | "REKLAMA" | "SZUM" | "ZRODLA";
type ChapterEntities = Partial<EntitiesByType>;

interface Sentence { index: number; text: string }
interface Section {
  position: number;
  title: string;
  type?: ChapterType;
  is_preamble?: boolean;
  sentence_count: number;
  sentences?: Sentence[];
}
interface EntityResponse {
  sections: { position: number; type: ChapterType; entities: ChapterEntities }[];
  has_entities: boolean;
}

const TYPE_LABELS: Record<ChapterType, string> = { TEMAT: "Treść", REKLAMA: "Reklama", SZUM: "Szum", ZRODLA: "Źródła" };
const KIND_LABELS: Record<HighlightKind, string> = { persName: "Osoby", place: "Miejsca", orgName: "Organizacje" };
const KIND_COLORS: Record<HighlightKind, string> = { persName: "#bfdbfe", place: "#bbf7d0", orgName: "#e2e8f0" };
const KINDS: HighlightKind[] = ["persName", "place", "orgName"];

const isShown = (item: EntityItem) => !item.is_country && item.place_verification_status !== "rejected";
const itemName = (item: EntityItem) => item.canonical_name ?? item.text;

// Entities of one chapter reduced to the kinds the reviewer wants to see (and, when a search
// text is set, to the entities whose name or a surface form contains it).
function filterEntities(entities: ChapterEntities | undefined, kinds: Set<HighlightKind>, query: string): ChapterEntities {
  const needle = query.trim().toLowerCase();
  const keep = (item: EntityItem) => isShown(item) && (!needle || [item.text, itemName(item), ...(item.variants ?? [])]
    .some((value) => value.toLowerCase().includes(needle)));
  return {
    persName: kinds.has("persName") ? (entities?.persName ?? []).filter(keep) : [],
    orgName: kinds.has("orgName") ? (entities?.orgName ?? []).filter(keep) : [],
    geogName: kinds.has("place") ? (entities?.geogName ?? []).filter(keep) : [],
    placeName: kinds.has("place") ? (entities?.placeName ?? []).filter(keep) : [],
  };
}

function highlightEntries(entities: ChapterEntities): HighlightEntry[] {
  const entry = (kind: HighlightKind) => (item: EntityItem): HighlightEntry => ({
    kind, label: itemName(item), variants: item.chapter_variants?.length ? item.chapter_variants : [item.text],
  });
  return [
    ...(entities.persName ?? []).map(entry("persName")),
    ...(entities.orgName ?? []).map(entry("orgName")),
    ...(entities.geogName ?? []).map(entry("place")),
    ...(entities.placeName ?? []).map(entry("place")),
  ];
}

// Country mentions stay out of the chip lists (they belong to the kraj-* pipeline) but the
// reviewer still needs to see which state a chapter is about, so they are shown separately.
function chapterCountries(entities: ChapterEntities | undefined): string[] {
  const names = [...(entities?.geogName ?? []), ...(entities?.placeName ?? []), ...(entities?.orgName ?? [])]
    .filter((item) => item.is_country && item.place_verification_status !== "rejected")
    .map(itemName);
  return [...new Set(names)];
}

const entityCount = (entities: ChapterEntities) =>
  (entities.persName?.length ?? 0) + (entities.orgName?.length ?? 0)
  + (entities.geogName?.length ?? 0) + (entities.placeName?.length ?? 0);

const chapterTitle = (section: Section) => (section.is_preamble || section.position === 0
  ? "Wstęp (przed pierwszym rozdziałem)"
  : `#${section.position} ${section.title}`);

const NerChapters = () => {
  const { id } = useParams();
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [sections, setSections] = React.useState<Section[]>([]);
  const [entityData, setEntityData] = React.useState<EntityResponse | null>(null);
  const [entityError, setEntityError] = React.useState(false);
  const [loadError, setLoadError] = React.useState("");
  const [doc, setDoc] = React.useState<{ title?: string; document_type?: string } | null>(null);
  const [version, setVersion] = React.useState(0);
  const [kinds, setKinds] = React.useState<Set<HighlightKind>>(new Set(KINDS));
  const [onlyWithEntities, setOnlyWithEntities] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [sectionsVersion, setSectionsVersion] = React.useState(0);
  const [merging, setMerging] = React.useState(false);
  const [mergeError, setMergeError] = React.useState("");
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);
  const base = `${apiUrl}/document/${id}`;

  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoadError("");
    axios.get<{ sections: Section[] }>(`${base}/chapter_sections`, { headers, params: { with_sentences: 1 } })
      .then((response) => { if (!cancelled) setSections(response.data.sections); })
      .catch((error) => {
        if (cancelled) return;
        const message = axios.isAxiosError(error) ? error.response?.data?.message : "";
        setLoadError(message === "Document has no transcript text"
          ? "Dokument nie ma tekstu transkrypcji."
          : "Nie udało się pobrać rozdziałów dokumentu.");
      });
    return () => { cancelled = true; };
  }, [id, base, headers, sectionsVersion]);

  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    axios.get(`${apiUrl}/website_get`, { headers, params: { id } })
      .then((response) => { if (!cancelled) setDoc(response.data); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [id, apiUrl, headers]);

  // Same endpoint and guards as the editor's chapter panel: the text is rewritten, so the
  // chapter list and the per-chapter entities are refetched afterwards.
  const mergeChapter = async (position: number, label: string) => {
    if (merging || !window.confirm(`Scalić ${label}? Numery kolejnych rozdziałów zmienią się.`)) return;
    setMerging(true);
    setMergeError("");
    try {
      await axios.post(`${base}/merge_chapter`, { position }, { headers });
      setSectionsVersion((current) => current + 1);
      setVersion((current) => current + 1);
    } catch (error) {
      const status = axios.isAxiosError(error) ? error.response?.status : undefined;
      setMergeError(status === 409
        ? "Nie można scalić: dokument ma embeddingi (otwórz go ponownie do edycji) albo trwa jego analiza."
        : "Nie udało się scalić rozdziałów.");
    } finally {
      setMerging(false);
    }
  };

  // Entities are refetched whenever the panel reports a change (detect, rename, delete,
  // merge, exclude) — it also reports its own first load, so this covers the initial fetch.
  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    axios.get<EntityResponse>(`${base}/chapter_entities`, { headers })
      .then((response) => { if (!cancelled) { setEntityData(response.data); setEntityError(false); } })
      .catch(() => { if (!cancelled) setEntityError(true); });
    return () => { cancelled = true; };
  }, [id, base, headers, version]);

  const toggleKind = (kind: HighlightKind) => setKinds((current) => {
    const next = new Set(current);
    if (next.has(kind)) next.delete(kind); else next.add(kind);
    return next;
  });

  const chapters = sections.map((section) => {
    const raw = entityData?.sections.find((item) => item.position === section.position);
    const type = raw?.type ?? section.type ?? "TEMAT";
    const entities = filterEntities(raw?.entities, kinds, query);
    return { section, type, entities, count: entityCount(entities), countries: type === "TEMAT" ? chapterCountries(raw?.entities) : [] };
  });
  const lastPosition = Math.max(0, ...sections.map((section) => section.position));
  // With a filter active only content chapters that still have matching entities stay listed;
  // without one every chapter is shown, skipped (ad/noise/source) chapters included.
  const loadingEntities = entityData === null && !entityError;
  const filtering = onlyWithEntities || query.trim() !== "";
  const visible = chapters.filter((chapter) => !filtering || (chapter.type === "TEMAT" && chapter.count > 0));
  const editorPath = `/${doc?.document_type || "youtube"}/${id}`;
  const scrollTo = (position: number) => (event: React.MouseEvent) => {
    event.preventDefault();
    document.getElementById(`ner-chapter-${position}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (!id) return null;

  return (
    <div>
      <h2 style={{ marginBottom: 4 }}>NER per rozdział</h2>
      <div style={{ color: "#475569", marginBottom: 8 }}>
        {doc?.title ? <strong>{doc.title}</strong> : `Dokument ${id}`}
        {" · "}<Link to={editorPath}>← Edytor</Link>
        {" · "}<Link to={`/chunks/${id}`}>Chunki →</Link>
        {" · "}<Link to={`/read/${id}`}>Czytnik</Link>
      </div>
      <div style={{ fontSize: "0.85em", color: "#64748b", marginBottom: 10 }}>
        Encje są zapisane dla całego dokumentu: poprawka (nazwa, usunięcie, wykluczenie, scalenie) dotyczy wszystkich
        rozdziałów. Rozdziały typu reklama, szum i źródła są pomijane przez NER (typ ustawisz w edytorze).
      </div>
      {loadError && <p role="alert" style={{ color: "#a33" }}>{loadError}</p>}
      {entityError && <p role="status" style={{ color: "#92400e" }}>Nie udało się pobrać encji rozdziałów.</p>}
      <div style={{ display: "grid", gridTemplateColumns: "230px minmax(0, 1fr)", gap: 16, alignItems: "start" }}>
        <nav aria-label="Rozdziały" style={{ position: "sticky", top: 8, maxHeight: "calc(100vh - 16px)", overflowY: "auto", fontSize: "0.85em" }}>
          {visible.map(({ section, type, count }) => (
            <div key={section.position} style={{ marginBottom: 6 }}>
              <a href={`#ner-chapter-${section.position}`} onClick={scrollTo(section.position)} style={{ textDecoration: "none" }}>
                {chapterTitle(section)}
              </a>
              <span style={{ color: "#64748b" }}>
                {type !== "TEMAT" ? ` · ${TYPE_LABELS[type]}` : loadingEntities ? "" : ` (${count})`}
              </span>
            </div>
          ))}
        </nav>
        <main style={{ minWidth: 0 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", marginBottom: 8 }}>
            {KINDS.map((kind) => (
              <label key={kind}>
                <input type="checkbox" checked={kinds.has(kind)} onChange={() => toggleKind(kind)} />{" "}
                <span style={{ background: KIND_COLORS[kind], padding: "0 4px", borderRadius: 3 }}>{KIND_LABELS[kind]}</span>
              </label>
            ))}
            <label>
              <input type="checkbox" checked={onlyWithEntities} onChange={(event) => setOnlyWithEntities(event.target.checked)} />{" "}
              Tylko rozdziały z encjami
            </label>
            <input type="search" value={query} placeholder="Szukaj encji…" aria-label="Szukaj encji"
              onChange={(event) => setQuery(event.target.value)} style={{ padding: "3px 8px" }} />
          </div>
          <EntitiesPanel
            docId={id}
            onEntitiesChanged={() => setVersion((current) => current + 1)}
            chapterRenderer={(renderGroups) => (
              <div>
                {entityData?.has_entities === false && (
                  <p style={{ color: "#667" }}>Brak zapisanych encji — użyj przycisku „Wykryj osoby, miejsca i obiekty”.</p>
                )}
                {mergeError && <p role="alert" style={{ color: "#a33" }}>{mergeError}</p>}
                {visible.map(({ section, type, entities, count, countries }) => (
                  <section key={section.position} id={`ner-chapter-${section.position}`} aria-label={chapterTitle(section)}
                    style={{ marginTop: 12, padding: 10, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                      <strong>{chapterTitle(section)}</strong>
                      {type !== "TEMAT" && (
                        <span style={{ fontSize: "0.8em", padding: "0 6px", borderRadius: 3, background: "#fef3c7" }}>
                          {TYPE_LABELS[type]}
                        </span>
                      )}
                      <span style={{ color: "#64748b", fontSize: "0.85em" }}>
                        {section.sentence_count} zdań · {loadingEntities ? "wczytuję encje…" : `${count} encji`}
                      </span>
                      {section.position >= 1 && (
                        <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                          {section.position >= 2 && (
                            <button type="button" disabled={merging} aria-label={`Scal rozdział ${section.position} z poprzednim`}
                              onClick={() => void mergeChapter(section.position, "ten rozdział z poprzednim")}>⇡ Scal z poprzednim</button>
                          )}
                          {section.position < lastPosition && (
                            <button type="button" disabled={merging} aria-label={`Scal rozdział ${section.position} z następnym`}
                              onClick={() => void mergeChapter(section.position + 1, "ten rozdział z następnym")}>⇣ Scal z następnym</button>
                          )}
                        </span>
                      )}
                    </div>
                    {type !== "TEMAT" ? (
                      <p style={{ color: "#667" }}>Rozdział pominięty w NER (typ: {TYPE_LABELS[type]}).</p>
                    ) : (
                      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)", gap: 14, marginTop: 8 }}>
                        <div style={{ lineHeight: 1.65, fontSize: "0.9em" }}>
                          {section.sentences?.map((sentence) => (
                            <span key={sentence.index}>
                              {splitByEntities(sentence.text, highlightEntries(entities)).map((segment, index) => (
                                segment.kind
                                  ? <mark key={index} title={`${segment.label} (${KIND_LABELS[segment.kind]})`}
                                    style={{ background: KIND_COLORS[segment.kind], padding: "0 2px", borderRadius: 3 }}>{segment.text}</mark>
                                  : <React.Fragment key={index}>{segment.text}</React.Fragment>
                              ))}{" "}
                            </span>
                          ))}
                        </div>
                        <div>
                          {renderGroups(entities)}
                          {countries.length > 0 && (
                            <div aria-label="Państwa rozdziału" style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "baseline" }}>
                              <strong style={{ fontSize: "0.85em" }}>Państwa:</strong>
                              {countries.map((country) => (
                                <span key={country} title="Państwo wspomniane w rozdziale"
                                  style={{ fontSize: "0.85em", padding: "0 6px", borderRadius: 3, background: "#fde68a" }}>
                                  🌍 {country}
                                </span>
                              ))}
                            </div>
                          )}
                          {loadingEntities && <small style={{ color: "#64748b" }}>Wczytuję encje…</small>}
                          {!loadingEntities && count === 0 && entityData?.has_entities !== false && (
                            <small style={{ color: "#64748b" }}>Brak encji w tym rozdziale.</small>
                          )}
                        </div>
                      </div>
                    )}
                  </section>
                ))}
                {visible.length === 0 && !loadError && sections.length > 0 && (
                  <p style={{ color: "#667" }}>Żaden rozdział nie spełnia filtrów.</p>
                )}
              </div>
            )}
          />
        </main>
      </div>
    </div>
  );
};

export default NerChapters;
