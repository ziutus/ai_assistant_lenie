import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";

// NER entities detected in the document (backend: GET/POST /website_entities,
// table document_entities — see docs/ner-integration-plan.md).

export interface EntityItem {
  id?: number;
  text: string;
  count: number;
  // Surface forms seen in the text ("Kijów", "Kijowa") — used server-side for
  // chapter-scoped filtering; not rendered
  variants?: string[];
  // Surface forms actually matched in the selected reader chapter.
  chapter_variants?: string[];
  // Linear infrastructure match (Overpass/OSM, infra_geometries cache) —
  // geojson is a MultiLineString drawn on the reader map
  pipeline?: {
    kind: string;
    substance?: string | null;
    name?: string | null;
    geojson?: { type: string; coordinates: [number, number][][] } | null;
  };
  // Stage-3 place verification (geogName/placeName only): absent = not checked,
  // true = geocoder confirmed (lat/lon/display_name present), false = not a real place
  verified?: boolean;
  lat?: number | null;
  lon?: number | null;
  display_name?: string;
  // Stage-4 person resolution (persName only): present when linked to a Person
  link_id?: number;
  person_id?: number;
  canonical_name?: string;
  person_description?: string | null;
  wikidata_qid?: string | null;
  confidence?: string;
  // Organization classified as an explicitly cited information source.
  information_source_id?: number;
  source_evidence?: string | null;
  // Global organization registry (orgName only) — present once resolved
  // (library/organization_registry.py). Lets the editor offer "Połącz z…".
  organization_id?: number;
}

interface EntitiesByType {
  persName: EntityItem[];
  orgName: EntityItem[];
  geogName: EntityItem[];
  placeName: EntityItem[];
}

interface PersonSearchResult {
  id: number;
  canonical_name: string;
  description: string | null;
  wikidata_qid: string | null;
  aliases: string[];
}

interface OrganizationSearchResult {
  id: number;
  canonical_name: string;
  aliases: string[];
  document_count: number;
}

const REVIEW_REASONS = [
  { code: "not_a_person", label: "To nie jest osoba ani miejsce" },
  { code: "misread_name", label: "Błędnie odczytana nazwa" },
  { code: "fictional_or_collective", label: "Osoba fikcyjna lub zbiorowa" },
  { code: "organization_as_person", label: "Organizacja rozpoznana jako osoba" },
  { code: "duplicate_person", label: "Duplikat innej osoby" },
  { code: "wrong_person", label: "Wskazano niewłaściwą osobę" },
  { code: "irrelevant", label: "Encja nieistotna dla dokumentu" },
  { code: "other", label: "Inny powód" },
] as const;

const chipStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  margin: "2px 4px 2px 0",
  borderRadius: "10px",
  background: "#e8eef7",
  border: "1px solid #b9c8de",
  fontSize: "0.85em",
};

const chipActionStyle: React.CSSProperties = {
  cursor: "pointer",
  marginLeft: 4,
  border: "none",
  background: "transparent",
  padding: 0,
  fontSize: "1em",
  lineHeight: 1,
};

export const EntityChips = ({
  label,
  items,
  linkPersons,
  linkInformationSources,
  searchUnresolvedPersons,
  actions,
  highlightMode,
  onHighlight,
}: {
  label: string;
  items: EntityItem[];
  // Resolved persons (person_id) become links to /persons/:id — used by the reader view.
  linkPersons?: boolean;
  linkInformationSources?: boolean;
  // Unresolved persons link to the registry search (/persons?q=) — stage 4
  // may not have run for the document yet, but the name is still searchable.
  searchUnresolvedPersons?: boolean;
  // Edit-mode buttons rendered inside each chip — used by the editor panel.
  actions?: (item: EntityItem) => React.ReactNode;
  // When true, every chip becomes a click-to-highlight button (calls
  // onHighlight instead of navigating) — used by the reader's mode toggle.
  highlightMode?: boolean;
  onHighlight?: (item: EntityItem) => void;
}) => {
  if (!items.length) {
    return null;
  }
  return (
    <div style={{ marginTop: "6px" }}>
      <strong>{label}:</strong>{" "}
      {items.map((item) => {
        const isResolvedPerson = item.person_id != null;
        const personTitle = isResolvedPerson
          ? [item.canonical_name, item.person_description, item.wikidata_qid, item.confidence]
              .filter(Boolean)
              .join(" | ")
          : undefined;
        const chip = (
          <span
            key={item.text}
            style={{
              ...chipStyle,
              ...(item.verified === true ? { background: "#e6f4ea", border: "1px solid #7cb98a" } : {}),
              ...(item.verified === false ? { opacity: 0.55 } : {}),
              ...(isResolvedPerson ? { background: "#e3edf9", border: "1px solid #7ba3d0" } : {}),
            }}
            title={personTitle ?? (item.verified === true ? item.display_name : item.verified === false ? "Geokoder nie potwierdził tego miejsca" : undefined)}
          >
            {item.text}
            {item.pipeline && <span title={`Rurociąg (${item.pipeline.substance ?? "?"}) — dane © OpenStreetMap`}> 🛢️</span>}
            {item.verified === true && <span style={{ color: "#2e7d43" }}> ✓</span>}
            {isResolvedPerson && (
              <span style={{ color: item.confidence === "manual_review" ? "#b45309" : "#1d5ca8" }}>
                {" "}{item.confidence === "manual_review" ? "?" : "✓"}
              </span>
            )}
            {item.count > 1 && <span style={{ color: "#667" }}> ×{item.count}</span>}
            {actions && actions(item)}
          </span>
        );
        if (highlightMode && onHighlight) {
          return (
            <button
              key={item.text}
              type="button"
              onClick={() => onHighlight(item)}
              title="Podświetl w tekście rozdziału"
              style={{ border: "none", background: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
            >
              {chip}
            </button>
          );
        }
        if (linkPersons && isResolvedPerson) {
          return (
            <Link key={item.text} to={`/persons/${item.person_id}`} style={{ textDecoration: "none" }}>
              {chip}
            </Link>
          );
        }
        if (linkInformationSources && item.information_source_id != null) {
          return (
            <Link
              key={item.text}
              to={`/information-sources?id=${item.information_source_id}`}
              style={{ textDecoration: "none" }}
              title={item.source_evidence ?? "Źródło cytowane w dokumencie"}
            >
              {chip}
            </Link>
          );
        }
        if (searchUnresolvedPersons && !isResolvedPerson) {
          return (
            <Link
              key={item.text}
              to={`/persons?q=${encodeURIComponent(item.text)}`}
              style={{ textDecoration: "none" }}
              title="Szukaj w rejestrze osób"
            >
              {chip}
            </Link>
          );
        }
        return chip;
      })}
    </div>
  );
};

const EntitiesPanel = ({
  docId,
  externalDisabled = false,
  onBusyChange,
  onEntitiesChanged,
}: {
  docId?: string | number;
  externalDisabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
  // Fires after a successful refresh/delete/merge/exclude — lets a host page
  // that keeps its own copy of this document's entities (e.g. read.tsx's
  // chapter-scoped sidebar) know it should refetch too.
  onEntitiesChanged?: () => void;
}) => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [entities, setEntities] = React.useState<EntitiesByType | null>(null);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [message, setMessage] = React.useState("");
  // Set when the last NER refresh found ner_service unreachable (backend:
  // web_documents.ner_unavailable_at) — lets us warn instead of implying
  // "no entities" when the real cause was a dead service.
  const [nerUnavailableAt, setNerUnavailableAt] = React.useState<string | null>(null);
  const [editMode, setEditMode] = React.useState(false);
  // "To inna osoba…" flow: chip whose person link is being re-pointed
  const [mergeFor, setMergeFor] = React.useState<EntityItem | null>(null);
  const [searchQ, setSearchQ] = React.useState("");
  const [searchResults, setSearchResults] = React.useState<PersonSearchResult[]>([]);
  // "Połącz z…" flow (orgName): chip being merged into another organization
  const [orgMergeFor, setOrgMergeFor] = React.useState<EntityItem | null>(null);
  const [orgSearchQ, setOrgSearchQ] = React.useState("");
  const [orgSearchResults, setOrgSearchResults] = React.useState<OrganizationSearchResult[]>([]);
  // "Połącz z innym miejscem" flow (geogName/placeName, or a misclassified
  // orgName mention of the same real-world place — e.g. "Kijów"): chip being
  // merged into a place entity of this same document. Per-document only,
  // unlike orgName merges — places have no cross-document registry.
  const [placeMergeFor, setPlaceMergeFor] = React.useState<EntityItem | null>(null);
  // "Dodaj alias" flow
  const [aliasFor, setAliasFor] = React.useState<EntityItem | null>(null);
  const [aliasText, setAliasText] = React.useState("");
  // "Wyklucz" flow: entity to suppress in future NER runs (ner_exclusions)
  const [excludeFor, setExcludeFor] = React.useState<{ item: EntityItem; entityType: string } | null>(null);
  const [deleteFor, setDeleteFor] = React.useState<EntityItem | null>(null);
  const [reviewReason, setReviewReason] = React.useState("");
  const [reviewComment, setReviewComment] = React.useState("");

  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "x-api-key": `${apiKey}`,
  };
  const jsonHeaders = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  const fetchEntities = React.useCallback(() => {
    if (!docId) {
      return;
    }
    axios
      .get(`${apiUrl}/website_entities`, { params: { id: docId }, headers })
      .then((response) => {
        setEntities(response.data.entities);
        setNerUnavailableAt(response.data.ner_unavailable_at ?? null);
        onEntitiesChanged?.();
      })
      .catch((error) => {
        console.error("Error fetching entities", error);
        setMessage("Nie udało się pobrać encji.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, apiUrl, apiKey]);

  React.useEffect(() => {
    setEntities(null);
    setMessage("");
    setEditMode(false);
    setMergeFor(null);
    setOrgMergeFor(null);
    setPlaceMergeFor(null);
    setAliasFor(null);
    setExcludeFor(null);
    setDeleteFor(null);
    setReviewReason("");
    setReviewComment("");
    fetchEntities();
  }, [docId, fetchEntities]);

  const handleRefresh = async () => {
    if (!docId) {
      return;
    }
    setIsRefreshing(true);
    onBusyChange?.(true);
    setMessage("");
    try {
      // First call after an ner_service restart loads the spaCy model (~90s) —
      // hence the generous timeout.
      const response = await axios.post(
        `${apiUrl}/website_entities`,
        { id: docId },
        { headers, timeout: 150000 },
      );
      setEntities(response.data.entities);
      setNerUnavailableAt(null);
      onEntitiesChanged?.();
      if (response.data.refreshed === 0) {
        setMessage("Nie wykryto żadnych osób ani miejsc w tym dokumencie.");
      }
    } catch (error: any) {
      console.error("Error refreshing entities", error);
      if (error.response?.data?.ner_unavailable) {
        setNerUnavailableAt(new Date().toISOString());
        setMessage("Serwis NER jest niedostępny — spróbuj ponownie za chwilę.");
      } else {
        setMessage(`Nie udało się wykryć encji: ${error.response?.data?.message || error.message}`);
      }
    }
    setIsRefreshing(false);
    onBusyChange?.(false);
  };

  const handleDelete = async () => {
    if (deleteFor?.id == null || !reviewReason) {
      return;
    }
    if (reviewReason === "other" && !reviewComment.trim()) {
      return;
    }
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/website_entities/${deleteFor.id}`, {
        headers: jsonHeaders,
        data: {
          decision: "rejected",
          reason_code: reviewReason,
          comment: reviewComment.trim() || null,
        },
      });
      setDeleteFor(null);
      setReviewReason("");
      setReviewComment("");
      fetchEntities();
    } catch (error: any) {
      console.error("Error deleting entity", error);
      setMessage(`Nie udało się usunąć encji: ${error.response?.data?.message || error.message}`);
    }
  };

  const handlePersonSearch = async (q: string) => {
    setSearchQ(q);
    if (q.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    try {
      const response = await axios.get(`${apiUrl}/persons`, { params: { q }, headers });
      setSearchResults(response.data.persons ?? []);
    } catch (error) {
      console.error("Error searching persons", error);
    }
  };

  const handleMergePick = async (target: PersonSearchResult) => {
    if (!mergeFor?.link_id) {
      return;
    }
    setMessage("");
    try {
      await axios.patch(
        `${apiUrl}/document_persons/${mergeFor.link_id}`,
        { action: "merge", target_person_id: target.id },
        { headers: jsonHeaders },
      );
      setMergeFor(null);
      setSearchQ("");
      setSearchResults([]);
      fetchEntities();
    } catch (error: any) {
      console.error("Error merging person link", error);
      setMessage(`Nie udało się zmienić osoby: ${error.response?.data?.message || error.message}`);
    }
  };

  const handleOrgSearch = async (q: string) => {
    setOrgSearchQ(q);
    if (q.trim().length < 2) {
      setOrgSearchResults([]);
      return;
    }
    try {
      const response = await axios.get(`${apiUrl}/organizations`, { params: { q }, headers });
      setOrgSearchResults(response.data.entries ?? []);
    } catch (error) {
      console.error("Error searching organizations", error);
    }
  };

  const handleOrgMergePick = async (
    target: { targetEntityId?: number; targetOrganizationId?: number },
  ) => {
    if (orgMergeFor?.id == null) {
      return;
    }
    setMessage("");
    try {
      await axios.post(
        `${apiUrl}/document/${docId}/organizations/merge`,
        {
          source_entity_id: orgMergeFor.id,
          target_entity_id: target.targetEntityId,
          target_organization_id: target.targetOrganizationId,
          make_global_alias: true,
        },
        { headers: jsonHeaders },
      );
      setOrgMergeFor(null);
      setOrgSearchQ("");
      setOrgSearchResults([]);
      fetchEntities();
    } catch (error: any) {
      console.error("Error merging organization", error);
      setMessage(`Nie udało się połączyć organizacji: ${error.response?.data?.message || error.message}`);
    }
  };

  const handlePlaceMergePick = async (target: EntityItem) => {
    if (placeMergeFor?.id == null || target.id == null) {
      return;
    }
    setMessage("");
    try {
      await axios.post(
        `${apiUrl}/document/${docId}/places/merge`,
        { source_entity_id: placeMergeFor.id, target_entity_id: target.id },
        { headers: jsonHeaders },
      );
      setPlaceMergeFor(null);
      fetchEntities();
    } catch (error: any) {
      console.error("Error merging place", error);
      setMessage(`Nie udało się połączyć miejsc: ${error.response?.data?.message || error.message}`);
    }
  };

  const handleExclude = async (scope: "global" | "author") => {
    if (!excludeFor || !reviewReason || (reviewReason === "other" && !reviewComment.trim())) {
      return;
    }
    setMessage("");
    try {
      await axios.post(
        `${apiUrl}/ner_exclusions`,
        {
          entity_text: excludeFor.item.text,
          entity_type: excludeFor.entityType,
          scope,
          document_id: docId,
        },
        { headers: jsonHeaders },
      );
      if (excludeFor.item.id != null) {
        await axios.delete(`${apiUrl}/website_entities/${excludeFor.item.id}`, {
          headers: jsonHeaders,
          data: {
            decision: scope === "global" ? "excluded_global" : "excluded_author",
            reason_code: reviewReason,
            comment: reviewComment.trim() || null,
          },
        });
      }
      setExcludeFor(null);
      setReviewReason("");
      setReviewComment("");
      setMessage(`„${excludeFor.item.text}" wykluczono (${scope === "global" ? "globalnie" : "dla autora"}).`);
      fetchEntities();
    } catch (error: any) {
      console.error("Error excluding entity", error);
      setMessage(`Nie udało się wykluczyć: ${error.response?.data?.message || error.message}`);
    }
  };

  const handleAliasSubmit = async () => {
    if (!aliasFor?.person_id || !aliasText.trim()) {
      return;
    }
    setMessage("");
    try {
      await axios.post(
        `${apiUrl}/persons/${aliasFor.person_id}/aliases`,
        { alias: aliasText.trim() },
        { headers: jsonHeaders },
      );
      setAliasFor(null);
      setAliasText("");
      setMessage(`Alias dodany do: ${aliasFor.canonical_name}`);
    } catch (error: any) {
      console.error("Error adding alias", error);
      setMessage(`Nie udało się dodać aliasu: ${error.response?.data?.message || error.message}`);
    }
  };

  if (!docId) {
    return null;
  }

  const persons = entities?.persName ?? [];
  const organizations = entities?.orgName ?? [];
  const citedSources = organizations.filter((item) => item.information_source_id != null);
  const otherOrganizations = organizations.filter((item) => item.information_source_id == null);
  const places = [...(entities?.geogName ?? []), ...(entities?.placeName ?? [])];
  const isEmpty = !persons.length && !organizations.length && !places.length;
  const reviewFormValid = Boolean(reviewReason)
    && (reviewReason !== "other" || Boolean(reviewComment.trim()));

  const reviewFields = (
    <>
      <label style={{ display: "block", marginTop: 6 }}>
        Powód <span style={{ color: "#a33" }}>*</span>
        <select
          value={reviewReason}
          onChange={(event) => setReviewReason(event.target.value)}
          style={{ display: "block", marginTop: 3, padding: "4px 8px", minWidth: 300 }}
        >
          <option value="">Wybierz powód…</option>
          {REVIEW_REASONS.map((reason) => (
            <option key={reason.code} value={reason.code}>{reason.label}</option>
          ))}
        </select>
      </label>
      <label style={{ display: "block", marginTop: 6 }}>
        Komentarz {reviewReason === "other" ? <span style={{ color: "#a33" }}>*</span> : "(opcjonalny)"}
        <textarea
          value={reviewComment}
          onChange={(event) => setReviewComment(event.target.value)}
          placeholder="Co zostało rozpoznane błędnie?"
          rows={2}
          style={{ display: "block", marginTop: 3, padding: "4px 8px", width: "min(520px, 95%)" }}
        />
      </label>
    </>
  );

  const editActions = (entityType: string) => (item: EntityItem) => (
    <>
      <button
        type="button"
        style={{ ...chipActionStyle, color: "#a33" }}
        title="Usuń encję (dla osoby usuwa też powiązanie z rejestrem)"
        onClick={() => {
          setDeleteFor(item);
          setExcludeFor(null);
          setMergeFor(null);
          setOrgMergeFor(null);
          setPlaceMergeFor(null);
          setAliasFor(null);
          setReviewReason("");
          setReviewComment("");
        }}
      >
        ×
      </button>
      <button
        type="button"
        style={{ ...chipActionStyle }}
        title="Usuń i nie wykrywaj więcej (słownik wykluczeń NER)"
        onClick={() => {
          setExcludeFor({ item, entityType });
          setDeleteFor(null);
          setMergeFor(null);
          setOrgMergeFor(null);
          setPlaceMergeFor(null);
          setAliasFor(null);
          setReviewReason("");
          setReviewComment("");
        }}
      >
        🚫
      </button>
      {item.link_id != null && (
        <button
          type="button"
          style={{ ...chipActionStyle, color: "#1d5ca8" }}
          title="To inna osoba — wskaż właściwą w rejestrze"
          onClick={() => { setMergeFor(item); setAliasFor(null); setSearchQ(""); setSearchResults([]); }}
        >
          ↷
        </button>
      )}
      {entityType === "orgName" && item.organization_id != null && (
        <button
          type="button"
          style={{ ...chipActionStyle, color: "#1d5ca8" }}
          title="Połącz z inną organizacją (globalnie, dla wszystkich dokumentów)"
          onClick={() => {
            setOrgMergeFor(item);
            setDeleteFor(null);
            setExcludeFor(null);
            setMergeFor(null);
            setPlaceMergeFor(null);
            setAliasFor(null);
            setOrgSearchQ("");
            setOrgSearchResults([]);
          }}
        >
          ↷
        </button>
      )}
      {entityType === "orgName" && item.id != null && places.length > 0 && (
        <button
          type="button"
          style={{ ...chipActionStyle, color: "#1d5ca8" }}
          title="To nie organizacja, tylko miejsce — połącz z miejscem w tym dokumencie"
          onClick={() => {
            setPlaceMergeFor(item);
            setDeleteFor(null);
            setExcludeFor(null);
            setMergeFor(null);
            setOrgMergeFor(null);
            setAliasFor(null);
          }}
        >
          🗺️
        </button>
      )}
      {entityType === "*" && item.id != null && places.filter((p) => p.id !== item.id).length > 0 && (
        <button
          type="button"
          style={{ ...chipActionStyle, color: "#1d5ca8" }}
          title="Połącz z innym miejscem w tym dokumencie"
          onClick={() => {
            setPlaceMergeFor(item);
            setDeleteFor(null);
            setExcludeFor(null);
            setMergeFor(null);
            setOrgMergeFor(null);
            setAliasFor(null);
          }}
        >
          ↷
        </button>
      )}
      {item.person_id != null && (
        <button
          type="button"
          style={{ ...chipActionStyle, color: "#2e7d43" }}
          title="Dodaj alias (przezwisko) do tej osoby"
          onClick={() => { setAliasFor(item); setMergeFor(null); setAliasText(""); }}
        >
          +
        </button>
      )}
    </>
  );

  return (
    <div style={{ marginTop: "10px", padding: "8px", border: "1px solid #ddd", borderRadius: "6px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <strong>Osoby i miejsca (NER)</strong>
        <button className={"button"} type="button" disabled={isRefreshing || externalDisabled} onClick={handleRefresh}>
          {isRefreshing ? "Wykrywam..." : "Wykryj osoby i miejsca"}
        </button>
        {!isEmpty && (
          <button className={"button"} type="button" onClick={() => { setEditMode(!editMode); setMergeFor(null); setOrgMergeFor(null); setPlaceMergeFor(null); setAliasFor(null); setExcludeFor(null); setDeleteFor(null); }}>
            {editMode ? "Zakończ edycję" : "Edytuj"}
          </button>
        )}
      </div>
      {nerUnavailableAt && (
        <div style={{
          marginTop: 8, padding: 8, background: "#fff7ed", border: "1px solid #fdba74",
          borderRadius: 6, fontSize: "0.85em", color: "#9a3412",
        }}>
          ⚠️ Serwis NER był niedostępny ({new Date(nerUnavailableAt).toLocaleString("pl-PL")}) — lista poniżej
          może być pusta lub niepełna niezależnie od zawartości dokumentu. Spróbuj ponownie za chwilę.
        </div>
      )}
      <EntityChips label={"Osoby"} items={persons} actions={editMode ? editActions("persName") : undefined} />
      <EntityChips
        label={"Źródła cytowane"}
        items={citedSources}
        linkInformationSources
        actions={editMode ? editActions("orgName") : undefined}
      />
      <EntityChips
        label={"Organizacje"}
        items={otherOrganizations}
        actions={editMode ? editActions("orgName") : undefined}
      />
      <EntityChips label={"Miejsca"} items={places} actions={editMode ? editActions("*") : undefined} />

      {editMode && deleteFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#fff4f0", borderRadius: 6 }}>
          <div>Usuń „{deleteFor.text}” i zapisz informację o błędzie:</div>
          {reviewFields}
          <button
            className={"button"}
            type="button"
            disabled={!reviewFormValid}
            style={{ marginTop: 8 }}
            onClick={handleDelete}
          >
            Usuń encję
          </button>
          <button
            type="button"
            style={{ ...chipActionStyle, marginLeft: 8 }}
            onClick={() => setDeleteFor(null)}
          >
            ✕ anuluj
          </button>
        </div>
      )}

      {editMode && excludeFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#fff4f0", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Nie wykrywaj więcej „{excludeFor.item.text}":
          </div>
          {reviewFields}
          <button className={"button"} type="button" disabled={!reviewFormValid} style={{ marginTop: 8 }} onClick={() => handleExclude("global")}>
            Globalnie
          </button>
          <button className={"button"} type="button" disabled={!reviewFormValid} style={{ marginLeft: 8, marginTop: 8 }} onClick={() => handleExclude("author")}>
            Tylko dla autora tego dokumentu
          </button>
          <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setExcludeFor(null)}>✕ anuluj</button>
        </div>
      )}

      {editMode && mergeFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            „{mergeFor.text}" to inna osoba — wyszukaj właściwą w rejestrze:
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setMergeFor(null)}>✕ anuluj</button>
          </div>
          <input
            value={searchQ}
            onChange={(e) => handlePersonSearch(e.target.value)}
            placeholder="Nazwisko osoby…"
            style={{ padding: "4px 8px", width: 260 }}
          />
          {searchResults.filter((p) => p.id !== mergeFor.person_id).map((p) => (
            <div key={p.id} style={{ padding: "3px 0" }}>
              <button className={"button"} type="button" onClick={() => handleMergePick(p)}>wybierz</button>
              {" "}<strong>{p.canonical_name}</strong>
              {p.description && <span style={{ color: "#667" }}> — {p.description}</span>}
              {p.wikidata_qid && <span style={{ color: "#999" }}> ({p.wikidata_qid})</span>}
            </div>
          ))}
        </div>
      )}

      {editMode && orgMergeFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Połącz „{orgMergeFor.text}" z inną organizacją (globalnie — obowiązuje też w przyszłych dokumentach):
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setOrgMergeFor(null)}>✕ anuluj</button>
          </div>
          {organizations.filter((o) => o.id !== orgMergeFor.id).length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ color: "#667", fontSize: "0.85em" }}>W tym dokumencie:</div>
              {organizations.filter((o) => o.id !== orgMergeFor.id).map((o) => (
                <div key={o.id} style={{ padding: "3px 0" }}>
                  <button className={"button"} type="button" onClick={() => handleOrgMergePick({ targetEntityId: o.id })}>
                    wybierz
                  </button>
                  {" "}<strong>{o.text}</strong>
                </div>
              ))}
            </div>
          )}
          <div style={{ color: "#667", fontSize: "0.85em" }}>Albo szukaj w globalnym rejestrze:</div>
          <input
            value={orgSearchQ}
            onChange={(e) => handleOrgSearch(e.target.value)}
            placeholder="Nazwa organizacji…"
            style={{ padding: "4px 8px", width: 260 }}
          />
          {orgSearchResults.filter((o) => o.id !== orgMergeFor.organization_id).map((o) => (
            <div key={o.id} style={{ padding: "3px 0" }}>
              <button className={"button"} type="button" onClick={() => handleOrgMergePick({ targetOrganizationId: o.id })}>
                wybierz
              </button>
              {" "}<strong>{o.canonical_name}</strong>
              {o.aliases.length > 0 && <span style={{ color: "#667" }}> ({o.aliases.join(", ")})</span>}
              <span style={{ color: "#999" }}> — {o.document_count} dok.</span>
            </div>
          ))}
        </div>
      )}

      {editMode && placeMergeFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Połącz „{placeMergeFor.text}" z innym miejscem w tym dokumencie:
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setPlaceMergeFor(null)}>✕ anuluj</button>
          </div>
          {places.filter((p) => p.id !== placeMergeFor.id).map((p) => (
            <div key={p.id} style={{ padding: "3px 0" }}>
              <button className={"button"} type="button" onClick={() => handlePlaceMergePick(p)}>wybierz</button>
              {" "}<strong>{p.text}</strong>
            </div>
          ))}
        </div>
      )}

      {editMode && aliasFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0fff4", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Nowy alias dla: <strong>{aliasFor.canonical_name ?? aliasFor.text}</strong>
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setAliasFor(null)}>✕ anuluj</button>
          </div>
          <input
            value={aliasText}
            onChange={(e) => setAliasText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAliasSubmit(); } }}
            placeholder="np. przezwisko z podkastu"
            style={{ padding: "4px 8px", width: 260 }}
          />
          <button className={"button"} type="button" style={{ marginLeft: 8 }} onClick={handleAliasSubmit}>
            Dodaj
          </button>
        </div>
      )}

      {isEmpty && !message && (
        <div style={{ marginTop: "6px", color: "#667" }}>
          Brak zapisanych encji — użyj przycisku, aby je wykryć.
        </div>
      )}
      {message && <div style={{ marginTop: "6px", color: "#a33" }}>{message}</div>}
    </div>
  );
};

export default EntitiesPanel;
