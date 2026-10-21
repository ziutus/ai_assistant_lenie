import React from "react";
import axios from "axios";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import EntitiesPanel, { type EntitiesByType, type EntityItem } from "../components/EntitiesPanel/entitiesPanel";
import ChannelBadge from "../components/ChannelBadge";
import ChapterDescriptionsPanel from "../components/ChapterDescriptionsPanel/chapterDescriptionsPanel";
import SelectionEntityMenu, { selectedFragment } from "../components/SelectionEntityMenu/selectionEntityMenu";
import EventDescriptionDialog from "../components/EventDescriptionDialog/eventDescriptionDialog";
import { splitByEntities, type HighlightEntry, type HighlightKind } from "../utils/entityHighlight";

type ChapterType = "TEMAT" | "REKLAMA" | "SZUM" | "ZRODLA";
// Events (eventName) and products/systems (productName) are added by hand from selected text; the shared panel
// does not draw them.
type ChapterEntities = Partial<EntitiesByType> & { eventName?: EntityItem[]; productName?: EntityItem[] };

interface Sentence { index: number; text: string }
interface Section {
  position: number;
  title: string;
  type?: ChapterType;
  is_preamble?: boolean;
  sentence_count: number;
  sentences?: Sentence[];
}
// A named group of states found in the chapter text ("państwa bałtyckie") with its member countries.
interface CountryGroup { name: string; members: string[]; variants: string[]; count: number }
interface EntityResponse {
  sections: { position: number; type: ChapterType; entities: ChapterEntities; country_groups?: CountryGroup[] }[];
  has_entities: boolean;
}

const TYPE_LABELS: Record<ChapterType, string> = { TEMAT: "Treść", REKLAMA: "Reklama", SZUM: "Szum", ZRODLA: "Źródła" };
const KIND_LABELS: Record<HighlightKind, string> = {
  persName: "Osoby", place: "Miejsca", orgName: "Organizacje", country: "Państwa", event: "Wydarzenia",
  product: "Produkty i systemy",
};
const KIND_COLORS: Record<HighlightKind, string> = {
  persName: "#bfdbfe", place: "#bbf7d0", orgName: "#e2e8f0", country: "#fde68a", event: "#fbcfe8",
  product: "#ddd6fe",
};
const KINDS: HighlightKind[] = ["persName", "place", "orgName", "country", "event", "product"];

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
    eventName: kinds.has("event") ? (entities?.eventName ?? []).filter(keep) : [],
    productName: kinds.has("product") ? (entities?.productName ?? []).filter(keep) : [],
  };
}

function highlightEntries(entities: ChapterEntities): HighlightEntry[] {
  const entry = (kind: HighlightKind) => (item: EntityItem): HighlightEntry => ({
    kind, label: itemName(item), variants: item.chapter_variants?.length ? item.chapter_variants : [item.text],
    ...(item.description ? { hint: item.description } : {}),
  });
  return [
    ...(entities.persName ?? []).map(entry("persName")),
    ...(entities.orgName ?? []).map(entry("orgName")),
    ...(entities.geogName ?? []).map(entry("place")),
    ...(entities.placeName ?? []).map(entry("place")),
    ...(entities.eventName ?? []).map(entry("event")),
    ...(entities.productName ?? []).map(entry("product")),
  ];
}

// Country mentions stay out of the chip lists (they belong to the kraj-* pipeline) but the
// reviewer still needs to see which state a chapter is about, so they are shown separately.
function countryItems(entities: ChapterEntities | undefined): EntityItem[] {
  return [...(entities?.geogName ?? []), ...(entities?.placeName ?? []), ...(entities?.orgName ?? [])]
    .filter((item) => item.is_country && item.place_verification_status !== "rejected");
}

const chapterCountries = (entities: ChapterEntities | undefined): string[] => [...new Set(countryItems(entities).map(itemName))];

// Countries matching the search text, highlighted in the sentences like the other kinds.
function highlightCountries(entities: ChapterEntities | undefined, kinds: Set<HighlightKind>, query: string): HighlightEntry[] {
  if (!kinds.has("country")) return [];
  const needle = query.trim().toLowerCase();
  return countryItems(entities)
    .filter((item) => !needle || [item.text, itemName(item), ...(item.variants ?? [])].some((value) => value.toLowerCase().includes(needle)))
    .map((item) => ({ kind: "country" as const, label: itemName(item), variants: item.chapter_variants?.length ? item.chapter_variants : [item.text] }));
}

// Groups of states matching the search text (name, member or surface form), highlighted like countries.
function visibleGroups(groups: CountryGroup[] | undefined, kinds: Set<HighlightKind>, query: string): CountryGroup[] {
  if (!kinds.has("country")) return [];
  const needle = query.trim().toLowerCase();
  return (groups ?? []).filter((group) => !needle
    || [group.name, ...group.members, ...group.variants].some((value) => value.toLowerCase().includes(needle)));
}

const groupHighlights = (groups: CountryGroup[]): HighlightEntry[] => groups.map((group) => ({
  kind: "country" as const, label: group.name, variants: group.variants, hint: `Obejmuje: ${group.members.join(", ")}`,
}));

const entityCount = (entities: ChapterEntities) =>
  (entities.persName?.length ?? 0) + (entities.orgName?.length ?? 0)
  + (entities.geogName?.length ?? 0) + (entities.placeName?.length ?? 0) + (entities.eventName?.length ?? 0)
  + (entities.productName?.length ?? 0);

const allItems = (entities: ChapterEntities | undefined): EntityItem[] =>
  [entities?.persName, entities?.orgName, entities?.geogName, entities?.placeName, entities?.eventName,
    entities?.productName].flatMap((items) => items ?? []);

// Entities that appear in the given chapter and in no other content (TEMAT) chapter: once the
// chapter is marked as noise these have no mention left in the text NER is run on.
function entitiesOnlyIn(data: EntityResponse | null, position: number): EntityItem[] {
  if (!data) return [];
  const elsewhere = new Set(data.sections
    .filter((section) => section.position !== position && section.type === "TEMAT")
    .flatMap((section) => allItems(section.entities).map((item) => item.id)));
  const own = data.sections.find((section) => section.position === position);
  return allItems(own?.entities).filter((item) => item.id !== undefined && !elsewhere.has(item.id));
}

const chapterTitle = (section: Section) => (section.is_preamble || section.position === 0
  ? "Wstęp (przed pierwszym rozdziałem)"
  : `#${section.position} ${section.title}`);

type GlossaryInfo = {
  author: string | null;
  entries: { id: number; canonical_name: string; aliases: string[]; fuzzy: boolean }[];
  applications: { original_text: string; replacement_text: string; occurrences: number }[];
};

const NerChapters = () => {
  const { id, chapter } = useParams();
  const navigate = useNavigate();
  const position = chapter === undefined ? undefined : (/^\d+$/.test(chapter) ? Number(chapter) : NaN);
  const chapterMode = chapter !== undefined;
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [sections, setSections] = React.useState<Section[]>([]);
  const [entityData, setEntityData] = React.useState<EntityResponse | null>(null);
  const [entityError, setEntityError] = React.useState(false);
  const [loadError, setLoadError] = React.useState("");
  const [doc, setDoc] = React.useState<{ title?: string; document_type?: string; byline?: string } | null>(null);
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
    axios.get<{ sections: Section[] }>(`${base}/chapter_sections`, { headers, params: chapterMode ? { position } : { with_sentences: 1 } })
      .then((response) => { if (!cancelled) setSections(response.data.sections); })
      .catch((error) => {
        if (cancelled) return;
        const message = axios.isAxiosError(error) ? error.response?.data?.message : "";
        setLoadError(message === "Document has no transcript text"
          ? "Dokument nie ma tekstu transkrypcji."
          : "Nie udało się pobrać rozdziałów dokumentu.");
      });
    return () => { cancelled = true; };
  }, [id, base, headers, sectionsVersion, chapterMode, position]);

  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    axios.get(`${apiUrl}/website_get`, { headers, params: { id } })
      .then((response) => { if (!cancelled) setDoc(response.data); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [id, apiUrl, headers]);

  // The channel's name glossary (speech-to-text repairs applied before NER) and what it changed here.
  const [glossary, setGlossary] = React.useState<GlossaryInfo | null>(null);
  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    axios.get<GlossaryInfo>(`${apiUrl}/ner_channel_glossary/applications`, { headers, params: { document_id: id } })
      .then((response) => { if (!cancelled) setGlossary(response.data); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [id, apiUrl, headers, chapterMode ? 0 : version]);

  const refreshChapters = async (preferredPosition: number) => {
    if (chapterMode) {
      const response = await axios.get<{ sections: Section[] }>(`${base}/chapter_sections`, { headers });
      const available = response.data.sections;
      setSections(available);
      const target = available.find((section) => section.position === preferredPosition)
        ?? available[available.length - 1];
      if (target && target.position !== position) {
        navigate(`/ner/${id}/${target.position}`, { replace: true });
        return;
      }
    }
    setSectionsVersion((current) => current + 1);
    setVersion((current) => current + 1);
  };

  // Same endpoint and guards as the editor's chapter panel: the text is rewritten, so the
  // chapter list and the per-chapter entities are refetched afterwards.
  const mergeChapter = async (position: number, label: string) => {
    if (merging || !window.confirm(`Scalić ${label}? Numery kolejnych rozdziałów zmienią się.`)) return;
    setMerging(true);
    setMergeError("");
    try {
      await axios.post(`${base}/merge_chapter`, { position }, { headers });
      await refreshChapters(position - 1);
    } catch (error) {
      const status = axios.isAxiosError(error) ? error.response?.status : undefined;
      setMergeError(status === 409
        ? "Nie można scalić: dokument ma embeddingi (otwórz go ponownie do edycji) albo trwa jego analiza."
        : "Nie udało się scalić rozdziałów.");
    } finally {
      setMerging(false);
    }
  };

  // Marks a content chapter as noise (same endpoint as the editor's type select) and then drops the
  // entities that were mentioned only there; entities shared with other chapters stay.
  const markAsNoise = async (position: number, label: string) => {
    if (merging) return;
    let fullData = entityData;
    if (chapterMode) {
      setMerging(true);
      try {
        fullData = (await axios.get<EntityResponse>(`${base}/chapter_entities`, { headers })).data;
      } catch {
        setMergeError("Nie udało się pobrać encji do oznaczenia rozdziału jako szum.");
        return;
      } finally {
        setMerging(false);
      }
    }
    const doomed = entitiesOnlyIn(fullData, position);
    if (!window.confirm(`Oznaczyć ${label} jako szum i usunąć ${doomed.length} encji występujących tylko w nim?`)) return;
    setMerging(true);
    setMergeError("");
    try {
      await axios.post(`${base}/chapter_type`, { position, type: "SZUM" }, { headers });
    } catch (error) {
      const status = axios.isAxiosError(error) ? error.response?.status : undefined;
      setMergeError(status === 409
        ? "Nie można zmienić typu: dokument ma embeddingi (otwórz go ponownie do edycji) albo trwa jego analiza."
        : "Nie udało się oznaczyć rozdziału jako szum.");
      setMerging(false);
      return;
    }
    let failed = 0;
    for (const item of doomed) {
      try {
        await axios.delete(`${apiUrl}/website_entities/${item.id}`, {
          headers, data: { decision: "deleted", reason_code: "irrelevant" },
        });
      } catch {
        failed += 1;
      }
    }
    if (failed > 0) setMergeError(`Rozdział oznaczono jako szum, ale nie udało się usunąć ${failed} z ${doomed.length} encji.`);
    try {
      await refreshChapters(position);
    } catch {
      setMergeError("Nie udało się odświeżyć rozdziałów.");
    } finally {
      setMerging(false);
    }
  };

  React.useEffect(() => {
    setEntityData(null);
    setEntityError(false);
    setFocus(null);
    setMentionMenu(null);
    setSelectionMenu(null);
    setDescribing(null);
  }, [id, chapter]);

  // Entities are refetched whenever the panel reports a change (detect, rename, delete,
  // merge, exclude) — it also reports its own first load, so this covers the initial fetch.
  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    axios.get<EntityResponse>(`${base}/chapter_entities`, { headers, ...(chapterMode ? { params: { position } } : {}) })
      .then((response) => { if (!cancelled) { setEntityData(response.data); setEntityError(false); } })
      .catch(() => { if (!cancelled) setEntityError(true); });
    return () => { cancelled = true; };
  }, [id, base, headers, version, chapterMode, position]);

  // "Podświetl w tekście" from a chip menu: that entity's mentions are marked strongly in every
  // chapter (whatever the kind filters say) and the view jumps to the first one.
  const [focus, setFocus] = React.useState<{ kind: HighlightKind; label: string; variants: string[] } | null>(null);
  const showInText = (item: EntityItem, kind: HighlightKind) => setFocus({
    kind, label: itemName(item), variants: [...new Set([item.text, ...(item.variants ?? []), ...(item.chapter_variants ?? [])])],
  });
  React.useEffect(() => {
    if (!focus) return;
    document.querySelector("[data-focus-mark]")?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [focus]);

  // Several spellings of one product ("Starlinka", "Starlinek", "Starling") fold into a single entity. The form lists
  // every product of the document (the chapter chips show only the chapter's own), the reviewer ticks the spellings
  // and names the result; `POST /document/:id/products/merge` keeps counts and spellings as variants.
  const [productMerge, setProductMerge] = React.useState<
    { items: EntityItem[]; selected: number[]; name: string; busy: boolean; error: string } | null>(null);
  const openProductMerge = async (seed: EntityItem) => {
    try {
      const response = await axios.get(`${apiUrl}/website_entities`, { params: { id }, headers });
      const items: EntityItem[] = (response.data?.entities?.productName ?? []).filter((item: EntityItem) => item.id !== undefined);
      setProductMerge({
        items, selected: seed.id !== undefined ? [seed.id] : [], name: itemName(seed), busy: false, error: "",
      });
    } catch {
      setMergeError("Nie udało się pobrać listy produktów.");
    }
  };
  const submitProductMerge = async () => {
    if (!productMerge || productMerge.selected.length < 2 || !productMerge.name.trim()) return;
    setProductMerge({ ...productMerge, busy: true, error: "" });
    try {
      await axios.post(`${apiUrl}/document/${id}/products/merge`,
        { entity_ids: productMerge.selected, name: productMerge.name.trim() }, { headers });
      setProductMerge(null);
      setVersion((current) => current + 1);
    } catch (error: any) {
      setProductMerge((current) => current && ({
        ...current, busy: false, error: error.response?.data?.message || "Nie udało się scalić produktów.",
      }));
    }
  };

  // The description dialog of an event: left click on its chip or right click on its mention in the text.
  const [describing, setDescribing] = React.useState<EntityItem | null>(null);
  const closeDescription = React.useCallback(() => setDescribing(null), []);
  const describeFromText = (item: EntityItem | undefined) => (event: React.MouseEvent) => {
    // A selected fragment keeps the "add entity" menu of the surrounding text.
    if (!item || item.id === undefined || selectedFragment(window.getSelection())) return;
    event.preventDefault();
    event.stopPropagation();
    setDescribing(item);
  };

  // A click on a highlighted person / organization / place / country in the text opens the chip's action menu
  // (retype, rename, delete, ...) right there, so the reviewer does not have to look for the chip in the side column.
  const [mentionMenu, setMentionMenu] = React.useState<
    { item: EntityItem; kind: "persName" | "orgName" | "place"; x: number; y: number; chapterPersons?: EntityItem[] } | null>(null);
  const closeMentionMenu = React.useCallback(() => setMentionMenu(null), []);
  const openMentionMenu = (position: number, segment: { kind?: HighlightKind; label?: string }) => (event: React.MouseEvent) => {
    // Selecting text (to add an entity) must not pop the menu.
    if (!segment.kind || selectedFragment(window.getSelection())) return;
    const raw = entityData?.sections.find((section) => section.position === position)?.entities;
    const places = [
      ...(raw?.geogName ?? []).map((item) => ({ ...item, entity_type: "geogName" as const })),
      ...(raw?.placeName ?? []).map((item) => ({ ...item, entity_type: "placeName" as const })),
    ];
    const candidates: { item: EntityItem; kind: "persName" | "orgName" | "place" }[] = segment.kind === "persName"
      ? (raw?.persName ?? []).map((item) => ({ item, kind: "persName" as const }))
      : segment.kind === "orgName"
        ? (raw?.orgName ?? []).filter((item) => !item.is_country).map((item) => ({ item, kind: "orgName" as const }))
        : segment.kind === "place"
          ? places.filter((item) => !item.is_country).map((item) => ({ item, kind: "place" as const }))
          : segment.kind === "country"
            ? [...places.filter((item) => item.is_country).map((item) => ({ item, kind: "place" as const })),
              ...(raw?.orgName ?? []).filter((item) => item.is_country).map((item) => ({ item, kind: "orgName" as const }))]
            : [];
    const found = candidates.find(({ item }) => itemName(item) === segment.label);
    if (!found || found.item.id === undefined) return;
    event.stopPropagation();
    setAddedMessage("");
    setMentionMenu({ ...found, x: event.clientX, y: event.clientY, chapterPersons: raw?.persName ?? [] });
  };

  // Right click on a selected fragment of the text opens the "add entity" menu; without a selection
  // (or over the chips, buttons and fields) the browser's own menu stays.
  const [selectionMenu, setSelectionMenu] = React.useState<{ x: number; y: number; text: string } | null>(null);
  const [panelKey, setPanelKey] = React.useState(0);
  const [addedMessage, setAddedMessage] = React.useState("");
  const closeSelectionMenu = React.useCallback(() => setSelectionMenu(null), []);
  const openSelectionMenu = (event: React.MouseEvent) => {
    const text = selectedFragment(window.getSelection());
    if (!text) return;
    event.preventDefault();
    setAddedMessage("");
    setSelectionMenu({ x: event.clientX, y: event.clientY, text });
  };

  const toggleKind = (kind: HighlightKind) => setKinds((current) => {
    const next = new Set(current);
    if (next.has(kind)) next.delete(kind); else next.add(kind);
    return next;
  });

  const chapters = sections.map((section) => {
    const raw = entityData?.sections.find((item) => item.position === section.position);
    const type = raw?.type ?? section.type ?? "TEMAT";
    const entities = filterEntities(raw?.entities, kinds, query);
    const groups = type === "TEMAT" ? visibleGroups(raw?.country_groups, kinds, query) : [];
    const countryHighlights = type === "TEMAT" ? [...highlightCountries(raw?.entities, kinds, query), ...groupHighlights(groups)] : [];
    return {
      section, type, entities, count: entityCount(entities), countryHighlights, groups,
      countries: type === "TEMAT" ? chapterCountries(raw?.entities) : [],
    };
  });
  const lastPosition = Math.max(0, ...sections.map((section) => section.position));
  // With a filter active only content chapters that still have matching entities stay listed;
  // without one every chapter is shown, skipped (ad/noise/source) chapters included.
  const loadingEntities = entityData === null && !entityError;
  const filtering = onlyWithEntities || query.trim() !== "";
  const visible = chapters.filter((item) => chapterMode ? item.section.position === position
    : !filtering || (item.type === "TEMAT" && item.count + item.countryHighlights.length > 0));
  const selectedIndex = sections.findIndex((section) => section.position === position);
  const previous = sections[selectedIndex - 1];
  const next = selectedIndex >= 0 ? sections[selectedIndex + 1] : undefined;
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
        {doc?.byline?.trim() && <>{" "}<ChannelBadge channel={doc.byline} /></>}
        {" · "}<Link to={editorPath}>← Edytor</Link>
        {" · "}<Link to={`/chunks/${id}`}>Chunki →</Link>
        {" · "}<Link to={`/read/${id}`}>Czytnik</Link>
      </div>
      <div style={{ fontSize: "0.85em", color: "#64748b", marginBottom: 10 }}>
        Encje są zapisane dla całego dokumentu: poprawka (nazwa, usunięcie, wykluczenie, scalenie) dotyczy wszystkich
        rozdziałów. Rozdziały typu reklama, szum i źródła są pomijane przez NER (typ ustawisz w edytorze albo przyciskiem „Oznacz jako szum”, który usuwa też encje występujące tylko w tym rozdziale).
      </div>
      {glossary?.author && (
        <div role="note" aria-label="Słownik kanału"
          style={{ fontSize: "0.85em", background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 6, padding: "6px 10px", marginBottom: 10 }}>
          {glossary.entries.length > 0 ? <>
            📖 Obowiązuje słownik nazw kanału „{glossary.author}” ({glossary.entries.length}:{" "}
            {glossary.entries.map((entry) => entry.canonical_name).join(", ")}). Przed rozpoznawaniem encji kopia
            transkrypcji jest poprawiana (zapisany tekst się nie zmienia).
            {glossary.applications.length > 0
              ? <> Przy ostatnim odświeżeniu poprawiono:{" "}
                  {glossary.applications.map((app) => `${app.original_text} → ${app.replacement_text} ×${app.occurrences}`).join(", ")}.</>
              : " Przy ostatnim odświeżeniu nic nie wymagało poprawki (albo encje nie były jeszcze odświeżone po dodaniu wpisów)."}
          </> : <>Słownik nazw kanału „{glossary.author}” jest pusty — poprawki transkrypcji nie obowiązują.</>}
          {" "}<Link to={`/ner-glossary?author=${encodeURIComponent(glossary.author)}`}>Słownik kanału →</Link>
        </div>
      )}
      {loadError && <p role="alert" style={{ color: "#a33" }}>{loadError}</p>}
      {entityError && <p role="status" style={{ color: "#92400e" }}>Nie udało się pobrać encji rozdziałów.</p>}
      <div style={{ display: "grid", gridTemplateColumns: "230px minmax(0, 1fr)", gap: 16, alignItems: "start" }}>
        <nav aria-label="Rozdziały" style={{ position: "sticky", top: 8, maxHeight: "calc(100vh - 16px)", overflowY: "auto", fontSize: "0.85em" }}>
          {(chapterMode ? chapters : visible).map(({ section, type, count }) => (
            <div key={section.position} style={{ marginBottom: 6 }}>
              {chapterMode ? <Link to={`/ner/${id}/${section.position}`}
                aria-current={section.position === position ? "page" : undefined}
                style={{ fontWeight: section.position === position ? "bold" : undefined }}>
                {chapterTitle(section)}
              </Link> : <a href={`#ner-chapter-${section.position}`} onClick={scrollTo(section.position)} style={{ textDecoration: "none" }}>
                {chapterTitle(section)}
              </a>}
              <span style={{ color: "#64748b" }}>
                {type !== "TEMAT" ? ` · ${TYPE_LABELS[type]}` : loadingEntities || (chapterMode && section.position !== position) ? "" : ` (${count})`}
              </span>
            </div>
          ))}
        </nav>
        <main style={{ minWidth: 0 }}>
          {chapterMode && <nav aria-label="Nawigacja rozdziału" style={{ display: "flex", gap: 16, marginBottom: 12 }}>
            {previous && <Link to={`/ner/${id}/${previous.position}`}>← Poprzedni</Link>}
            <Link to={`/ner/${id}`}>Wszystkie rozdziały</Link>
            {next && <Link to={`/ner/${id}/${next.position}`}>Następny →</Link>}
          </nav>}
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
          {focus && (
            <div role="status" style={{ marginBottom: 8, padding: "4px 10px", background: "#fef9c3", border: "1px solid #facc15", borderRadius: 6, fontSize: "0.9em" }}>
              🔎 Podświetlono w tekście: <strong>{focus.label}</strong>{" "}
              <button type="button" onClick={() => setFocus(null)}>✕ wyczyść</button>
            </div>
          )}
          {addedMessage && <div role="status" style={{ marginBottom: 8, color: "#166534" }}>{addedMessage}</div>}
          {productMerge && (
            <form aria-label="Scal produkty" style={{ marginBottom: 8, padding: "6px 10px", fontSize: "0.9em",
              background: "#f5f3ff", border: "1px solid #c4b5fd", borderRadius: 6 }}
              onSubmit={(event) => { event.preventDefault(); void submitProductMerge(); }}>
              <div>Zaznacz zapisy tego samego produktu (min. 2):</div>
              {productMerge.items.map((item) => (
                <label key={item.id} style={{ display: "inline-block", marginRight: 10 }}>
                  <input type="checkbox" checked={productMerge.selected.includes(item.id as number)}
                    onChange={(event) => setProductMerge({
                      ...productMerge,
                      selected: event.target.checked
                        ? [...productMerge.selected, item.id as number]
                        : productMerge.selected.filter((value) => value !== item.id),
                    })} /> {itemName(item)} ×{item.count}
                </label>
              ))}
              <div>
                <label>Nazwa po scaleniu:{" "}
                  <input aria-label="Nazwa produktu po scaleniu" value={productMerge.name}
                    onChange={(event) => setProductMerge({ ...productMerge, name: event.target.value })} />
                </label>{" "}
                <button type="submit"
                  disabled={productMerge.busy || productMerge.selected.length < 2 || !productMerge.name.trim()}>
                  Scal</button>{" "}
                <button type="button" onClick={() => setProductMerge(null)}>Anuluj</button>
                {productMerge.error && <span role="alert"> {productMerge.error}</span>}
              </div>
            </form>
          )}
          {describing && describing.id !== undefined && (
            <EventDescriptionDialog key={describing.id} entityId={describing.id} name={itemName(describing)}
              description={describing.description ?? null} apiUrl={apiUrl} headers={headers} onClose={closeDescription}
              onSaved={() => { setDescribing(null); setVersion((current) => current + 1); }} />
          )}
          {selectionMenu && (
            <SelectionEntityMenu {...selectionMenu} apiUrl={apiUrl} docId={id} headers={headers} byline={doc?.byline}
              onClose={closeSelectionMenu}
              onAdded={(message) => { setSelectionMenu(null); setAddedMessage(message); setPanelKey((current) => current + 1); setVersion((current) => current + 1); }} />
          )}
          <EntitiesPanel
            docId={id}
            refreshKey={panelKey}
            onShowInText={showInText}
            onDescribeEvent={setDescribing}
            onMergeProducts={(item) => void openProductMerge(item)}
            mentionMenu={mentionMenu}
            onMentionMenuClose={closeMentionMenu}
            onEntitiesChanged={() => setVersion((current) => current + 1)}
            chapterRenderer={(renderGroups) => (
              <div>
                {entityData?.has_entities === false && (
                  <p style={{ color: "#667" }}>Brak zapisanych encji — użyj przycisku „Wykryj osoby, miejsca i obiekty”.</p>
                )}
                {mergeError && <p role="alert" style={{ color: "#a33" }}>{mergeError}</p>}
                {visible.map(({ section, type, entities, count, countries, countryHighlights, groups }) => (
                  <section key={section.position} id={`ner-chapter-${section.position}`} aria-label={chapterTitle(section)}
                    style={{ marginTop: 12, padding: 10, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                      <strong>{chapterTitle(section)}</strong>
                      {!chapterMode && <Link to={`/ner/${id}/${section.position}`} style={{ fontSize: "0.85em" }}>
                        Tylko ten rozdział →
                      </Link>}
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
                          {type === "TEMAT" && (
                            <button type="button" disabled={merging || loadingEntities} aria-label={`Oznacz rozdział ${section.position} jako szum`}
                              onClick={() => void markAsNoise(section.position, "ten rozdział")}>🗑 Oznacz jako szum</button>
                          )}
                        </span>
                      )}
                    </div>
                    {type !== "TEMAT" ? (
                      <p style={{ color: "#667" }}>Rozdział pominięty w NER (typ: {TYPE_LABELS[type]}).</p>
                    ) : (
                      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)", gap: 14, marginTop: 8 }}>
                        <div style={{ lineHeight: 1.65, fontSize: "0.9em" }} onContextMenu={openSelectionMenu}>
                          {section.sentences?.map((sentence) => (
                            <span key={sentence.index}>
                              {splitByEntities(sentence.text, [
                                ...(focus ? [{ kind: focus.kind, label: focus.label, variants: focus.variants }] : []),
                                ...highlightEntries(entities), ...countryHighlights,
                              ]).map((segment, index) => {
                                if (!segment.kind) return <React.Fragment key={index}>{segment.text}</React.Fragment>;
                                const focused = focus !== null && segment.kind === focus.kind && segment.label === focus.label;
                                return <mark key={index} title={`${segment.label} (${KIND_LABELS[segment.kind]})${segment.hint ? ` — ${segment.hint}` : ""}`}
                                  {...(focused ? { "data-focus-mark": "" } : {})}
                                  {...(segment.kind === "event"
                                    ? { onContextMenu: describeFromText(entities.eventName?.find((item) => itemName(item) === segment.label)) }
                                    : { onClick: openMentionMenu(section.position, segment) })}
                                  style={{
                                    cursor: segment.kind === "event" || segment.kind === "product" ? undefined : "pointer",
                                    background: focused ? "#fde047" : KIND_COLORS[segment.kind], padding: "0 2px", borderRadius: 3,
                                    ...(focused ? { outline: "2px solid #d97706" } : {}),
                                  }}>{segment.text}</mark>;
                              })}{" "}
                            </span>
                          ))}
                        </div>
                        <div>
                          {renderGroups(entities)}
                          {id && <ChapterDescriptionsPanel apiUrl={apiUrl} apiKey={apiKey ?? ""} docId={id}
                            position={section.position} onSaved={() => setVersion((current) => current + 1)} />}
                          {(countries.length > 0 || groups.length > 0) && (
                            <div aria-label="Państwa rozdziału" style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "baseline" }}>
                              <strong style={{ fontSize: "0.85em" }}>Państwa:</strong>
                              {countries.map((country) => (
                                <span key={country} title="Państwo wspomniane w rozdziale"
                                  style={{ fontSize: "0.85em", padding: "0 6px", borderRadius: 3, background: "#fde68a" }}>
                                  🌍 {country}
                                </span>
                              ))}
                              {groups.map((group) => (
                                <span key={group.name} title={`Grupa państw: ${group.members.join(", ")}`}
                                  style={{ fontSize: "0.85em", padding: "0 6px", borderRadius: 3, background: "#fde68a", border: "1px dashed #d97706" }}>
                                  🌍 {group.name} ({group.members.join(", ")})
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
