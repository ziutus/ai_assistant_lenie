import React from "react";
import "./entitiesPanel.css";
import axios from "axios";
import { Link } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";
import { copyText } from "../../utils/copyText";
import { modelOptionText, type ModelOption } from "../../utils/modelDetails";
import type { CountryTag } from "../CountryMap/countryMap";
import InfoTip from "../InfoTip";
import RejectedPlaces from "./rejectedPlaces";
import OrganizationMergePreview, { type MergePreviewData } from "./organizationMergePreview";

// NER entities detected in the document (backend: GET/POST /website_entities,
// table document_entities — see docs/ner-integration-plan.md).

export type EntityRelevance = "central" | "related" | "figurative";

export interface EntityItem {
  relevance?: EntityRelevance;
  id?: number;
  text: string;
  count: number;
  // Reviewer-approved description (eventName entities only).
  description?: string | null;
  // Original NER category. Required when a combined "Miejsca" chip is
  // excluded, so a placeName rule does not turn into a wildcard rule.
  entity_type?: "persName" | "orgName" | "geogName" | "placeName";
  // True when country_gazetteer recognizes this entity's text as a country
  // name (geogName/placeName/orgName only) — geogName/placeName/orgName
  // country mentions are hidden from "Miejsca"/"Organizacje" here since the
  // reader's own "Państwa" block (kraj-* tags, LLM-vetted) already covers them.
  is_country?: boolean;
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
  // true = accepted geocoder result; false includes proposals awaiting human review.
  place_verification_status?: "needs_review" | "confirmed" | "rejected" | null;
  place_review_reason?: string | null;
  // Countries the place mention lists ("Pakistanem Afganistanem"); offered by the "Podziel" menu entry.
  split_suggestion?: string[];
  // Wikipedia article of the place from the cross-document place registry (/places).
  wikipedia_url?: string;
  proposed_geocode_id?: number;
  proposed_display_name?: string | null;
  proposed_lat?: number | null;
  proposed_lon?: number | null;
  verified?: boolean;
  lat?: number | null;
  lon?: number | null;
  display_name?: string;
  // Historical state or territory (Jugosławia, ZSRR...) resolved from the
  // curated gazetteer, not by the geocoder (library/historical_state_gazetteer.py).
  historical?: { year_from: number; year_to: number; successors: string };
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
  // The information source record behind a cited source (library/organization_source_sync.py).
  information_source_name?: string;
  information_source_type?: string | null;
  information_source_domain?: string | null;
  information_source_description?: string | null;
  // Global organization registry (orgName only) — present once resolved
  // (library/organization_registry.py). Lets the editor offer "Połącz z…".
  organization_id?: number;
  organization_link_id?: number;
  organization_review_status?: string;
  // Short explanation shown as a tooltip (e.g. "EDF — francuski operator
  // energetyczny") — Organization.description, edited via PATCH /organizations/<id>.
  organization_description?: string | null;
  // Rule-detected physical facility, built from a type phrase and a place.
  facility_type?: string;
  place_name?: string | null;
  facility_description?: string | null;
  operator_name?: string | null;
  source_url?: string | null;
}

export interface EntitiesByType {
  persName: EntityItem[];
  orgName: EntityItem[];
  geogName: EntityItem[];
  placeName: EntityItem[];
  facility?: EntityItem[];
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

interface EntityEnrichmentJob {
  id: string;
  status: "queued" | "running" | "done" | "failed" | "cancel_requested" | "cancelled";
  progress?: { stages?: Record<string, { label: string; current: number; total: number }> } | null;
  error?: string | null;
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

interface MenuEntry {
  label: string;
  action?: () => void;
  // Navigation entry (rendered as a router link) instead of an in-panel action.
  to?: string;
  // With `to`: open the page in a new browser tab (a plain link) so the reviewed text stays where it is.
  newTab?: boolean;
  // Submenu: the entry expands in place (no flyout, so it works on touch screens).
  children?: MenuEntry[];
}

// Tooltip for a chip that is a cited source: "gazeta · telegraph.co.uk · opis".
const sourceTitleOf = (item: EntityItem): string | undefined => {
  if (item.information_source_id == null) return undefined;
  const title = [
    item.information_source_type,
    item.information_source_domain,
    item.information_source_description ?? item.organization_description,
  ].filter(Boolean).join(" · ");
  return title || undefined;
};

const RELEVANCE_OPTIONS = [
  { value: "central", label: "Główny temat", title: "Bezpośrednio dotyczy głównego tematu dokumentu" },
  { value: "related", label: "Pośrednio", title: "Pośredni związek z tematem dokumentu" },
  { value: "figurative", label: "Przenośnie", title: "Wzmianka przenośna; miejsce nie jest pokazywane na mapie" },
] as const;

export const EntityChips = ({
  label,
  items,
  linkPersons,
  linkInformationSources,
  linkOrganizations,
  searchUnresolvedPersons,
  actions,
  highlightMode,
  onHighlight,
  menuActions,
}: {
  label: string;
  items: EntityItem[];
  // Resolved persons (person_id) become links to /persons/:id — used by the reader view.
  linkPersons?: boolean;
  linkInformationSources?: boolean;
  // Resolved organizations (organization_id) become links to /organizations/:id
  // — used by the reader view. Skipped when the chip is already a cited
  // information source link (linkInformationSources takes priority).
  linkOrganizations?: boolean;
  // Unresolved persons link to the registry search (/persons?q=) — stage 4
  // may not have run for the document yet, but the name is still searchable.
  searchUnresolvedPersons?: boolean;
  // Edit-mode buttons rendered inside each chip — used by the editor panel.
  actions?: (item: EntityItem) => React.ReactNode;
  menuActions?: (item: EntityItem) => MenuEntry[];
  // When true, every chip becomes a click-to-highlight button (calls
  // onHighlight instead of navigating) — used by the reader's mode toggle.
  highlightMode?: boolean;
  onHighlight?: (item: EntityItem) => void;
}) => {
  const [openMenu, setOpenMenu] = React.useState<string | null>(null);
  const menuRef = React.useRef<HTMLSpanElement>(null);
  const panelRef = React.useRef<HTMLSpanElement>(null);
  const [openSub, setOpenSub] = React.useState<string | null>(null);
  // Keeps a long menu on screen: opens upwards when there is more room above,
  // scrolls when it fits neither way, and right-aligns near the right edge.
  const [placement, setPlacement] = React.useState<{ up: boolean; right: boolean; maxHeight?: number }>(
    { up: false, right: false });
  const triggerRef = React.useRef<HTMLButtonElement | null>(null);
  React.useEffect(() => {
    if (openMenu === null) return;
    const outside = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpenMenu(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenMenu(null);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [openMenu]);
  React.useEffect(() => setOpenMenu(null), [items, menuActions]);
  React.useEffect(() => setOpenSub(null), [openMenu]);
  React.useLayoutEffect(() => {
    const panel = panelRef.current;
    const chip = menuRef.current;
    if (openMenu === null || !panel || !chip) return;
    const chipRect = chip.getBoundingClientRect();
    const below = window.innerHeight - chipRect.bottom - 8;
    const above = chipRect.top - 8;
    const height = panel.scrollHeight;
    const up = height > below && above > below;
    const room = up ? above : below;
    const next = {
      up,
      right: chipRect.left + panel.offsetWidth > window.innerWidth - 8,
      maxHeight: height > room ? Math.max(room, 120) : undefined,
    };
    setPlacement((prev) => (prev.up === next.up && prev.right === next.right && prev.maxHeight === next.maxHeight
      ? prev : next));
  }, [openMenu, openSub]);
  if (!items.length) {
    return null;
  }
  const alphabeticalItems = [...items].sort((a, b) => a.text.localeCompare(b.text, "pl"));
  return (
    <div style={{ marginTop: "6px" }}>
      <strong>{label}:</strong>{" "}
      {alphabeticalItems.map((item) => {
        const key = `${item.entity_type ?? ""}:${item.id ?? item.text}`;
        const entries = menuActions
          ? [{ label: "Kopiuj nazwę", action: () => void copyText(item.text) }, ...menuActions(item)]
          : [];
        const menuOpen = openMenu === key;
        const isResolvedPerson = item.person_id != null;
        const personTitle = isResolvedPerson
          ? [item.canonical_name, item.person_description, item.wikidata_qid, item.confidence]
              .filter(Boolean)
              .join(" | ")
          : undefined;
        const facilityTitle = item.facility_description
          ? [item.text, item.facility_description, item.operator_name && `Operator: ${item.operator_name}`]
              .filter(Boolean)
              .join(" | ")
          : undefined;
        const historicalTitle = item.historical
          ? `Państwo historyczne (${item.historical.year_from}–${item.historical.year_to}). Następcy: ${item.historical.successors}`
          : undefined;
        const isDimmed = item.verified === false && item.place_verification_status !== "needs_review";
        const chipContent = (
          <>
            {entries.length ? (
              <button type="button" aria-label={item.text} aria-haspopup="menu" aria-expanded={menuOpen}
                style={{ border: 0, background: "transparent", padding: 0, color: "inherit", font: "inherit", cursor: "pointer" }}
                onClick={(event) => { triggerRef.current = event.currentTarget; setOpenMenu(menuOpen ? null : key); }}>
                {item.text}
              </button>
            ) : item.text}
            {item.wikipedia_url && (
              <a href={item.wikipedia_url} target="_blank" rel="noopener noreferrer" title="Artykuł w Wikipedii"
                aria-label={`Wikipedia: ${item.text}`} style={{ textDecoration: "none" }}> 📖</a>
            )}
            {item.pipeline && <span title={`Rurociąg (${item.pipeline.substance ?? "?"}) — dane © OpenStreetMap`}> 🛢️</span>}
            {(item.organization_description || item.information_source_description) && (
              <span title={item.information_source_description ?? item.organization_description ?? undefined}
                style={{ color: "#667" }}> ℹ️</span>
            )}
            {item.facility_description && <span title={facilityTitle} style={{ color: "#667" }}> ℹ️</span>}
            {item.place_verification_status === "needs_review" && <span style={{ color: "#92400e" }}>
              {" "}Wymaga potwierdzenia
              {item.proposed_display_name && <span style={{ display: "block" }}>
                Propozycja lokalizacji: {item.proposed_display_name}
              </span>}
            </span>}
            {item.verified === true && !item.historical && <span style={{ color: "#2e7d43" }}> ✓</span>}
            {item.historical && <span style={{ color: "#a86a0a" }}> 🕰️</span>}
            {isResolvedPerson && (
              <span style={{ color: item.confidence === "manual_review" ? "#b45309" : "#1d5ca8" }}>
                {" "}{item.confidence === "manual_review" ? "?" : "✓"}
              </span>
            )}
            {item.count > 1 && <span style={{ color: "#667" }}> ×{item.count}</span>}
            {actions && actions(item)}
          </>
        );
        const chip = (
          <span
            key={key}
            ref={menuOpen ? menuRef : undefined}
            className={`entity-chip entity-chip--${item.relevance ?? "central"}`}
            style={{
              ...chipStyle,
              position: "relative",
              ...(isDimmed ? { background: "#e8eef78c", border: "1px solid #b9c8de8c" } : {}),
              ...(item.verified === true ? { background: "#e6f4ea", border: "1px solid #7cb98a" } : {}),
              ...(item.historical ? { background: isDimmed ? "#fdf3e18c" : "#fdf3e1",
                border: isDimmed ? "1px solid #d9a4418c" : "1px solid #d9a441" } : {}),
              ...(isResolvedPerson ? { background: isDimmed ? "#e3edf98c" : "#e3edf9",
                border: isDimmed ? "1px solid #7ba3d08c" : "1px solid #7ba3d0" } : {}),
              ...(item.relevance && item.relevance !== "central" ? { background: undefined, border: undefined } : {}),
            }}
            title={(item.relevance && item.relevance !== "central"
              ? RELEVANCE_OPTIONS.find((option) => option.value === item.relevance)?.title : undefined)
              ?? historicalTitle ?? personTitle
              ?? sourceTitleOf(item)
              ?? item.organization_description
              ?? facilityTitle
              ?? (item.place_verification_status === "needs_review" ? "Wymaga potwierdzenia" : undefined)
              ?? (item.verified === true ? item.display_name : item.verified === false ? "Geokoder nie potwierdził tego miejsca" : undefined)}
          >
            {isDimmed ? <span style={{ opacity: 0.55 }}>{chipContent}</span> : chipContent}
            {menuOpen && entries.length > 0 && (
              <span role="menu" ref={panelRef} aria-label={`Działania: ${item.text}`}
                style={{ position: "absolute", ...(placement.up ? { bottom: "100%" } : { top: "100%" }),
                  ...(placement.right ? { right: 0 } : { left: 0 }), zIndex: 10, padding: 4,
                  background: "white", border: "1px solid #b9c8de", borderRadius: 6, minWidth: 230,
                  maxWidth: "calc(100vw - 16px)", maxHeight: placement.maxHeight, overflowY: "auto",
                  boxShadow: "0 2px 8px #0002" }}>
                {entries.map((entry) => {
                  const itemStyle: React.CSSProperties = { display: "block", width: "100%", textAlign: "left",
                    padding: "6px 8px", boxSizing: "border-box" };
                  if (entry.to && entry.newTab) {
                    return (
                      <a key={entry.label} role="menuitem" href={entry.to} target="_blank" rel="noopener noreferrer"
                        onClick={() => setOpenMenu(null)} style={{ ...itemStyle, color: "inherit", textDecoration: "none" }}>
                        {entry.label}
                      </a>
                    );
                  }
                  if (entry.to) {
                    return (
                      <Link key={entry.label} role="menuitem" to={entry.to} onClick={() => setOpenMenu(null)}
                        style={{ ...itemStyle, color: "inherit", textDecoration: "none" }}>
                        {entry.label}
                      </Link>
                    );
                  }
                  if (entry.children) {
                    const subOpen = openSub === entry.label;
                    return (
                      <React.Fragment key={entry.label}>
                        <button type="button" role="menuitem" aria-haspopup="menu" aria-expanded={subOpen}
                          style={{ ...itemStyle, background: "transparent", border: 0, cursor: "pointer" }}
                          onClick={() => setOpenSub(subOpen ? null : entry.label)}>
                          {entry.label} {subOpen ? "▾" : "▸"}
                        </button>
                        {subOpen && entry.children.map((child) => (
                          <button key={child.label} type="button" role="menuitem"
                            style={{ ...itemStyle, paddingLeft: 24, background: "transparent", border: 0,
                              cursor: "pointer" }}
                            onClick={() => { setOpenMenu(null); child.action?.(); }}>
                            {child.label}
                          </button>
                        ))}
                      </React.Fragment>
                    );
                  }
                  return (
                    <button key={entry.label} type="button" role="menuitem"
                      style={{ ...itemStyle, background: "transparent", border: 0, cursor: "pointer" }}
                      onClick={() => { setOpenMenu(null); entry.action?.(); }}>
                      {entry.label}
                    </button>
                  );
                })}
              </span>
            )}
          </span>
        );
        if (entries.length) return chip;
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
        if (linkOrganizations && item.organization_id != null && item.information_source_id == null) {
          return (
            <Link
              key={item.text}
              to={`/organizations/${item.organization_id}`}
              style={{ textDecoration: "none" }}
              title={item.organization_description ?? "Otwórz w rejestrze organizacji"}
            >
              {chip}
            </Link>
          );
        }
        if (item.source_url) {
          return (
            <a
              key={item.text}
              href={item.source_url}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: "none" }}
              title="Otwórz źródło i więcej informacji o obiekcie"
            >
              {chip}
            </a>
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
  countries: providedCountries,
  refreshKey = 0,
  chapterRenderer,
  onShowInText,
  mentionMenu,
  onMentionMenuClose,
}: {
  docId?: string | number;
  // A click on a highlighted mention in the text (the /ner/:id page): opens the same action menu a
  // chip has, at the click point. The host passes a fresh object per click and clears it on close.
  mentionMenu?: {
    item: EntityItem; kind: "persName" | "orgName" | "place"; x: number; y: number; chapterPersons?: EntityItem[];
  } | null;
  onMentionMenuClose?: () => void;
  // When set, every chip menu offers "Podświetl w tekście" and calls this with the chip's entity
  // and its kind (the /ner/:id page marks that entity's mentions in the transcript).
  onShowInText?: (item: EntityItem, kind: "persName" | "orgName" | "place") => void;
  // Chapter mode (the /ner/:id page): the host draws the entity groups itself, once per
  // chapter, through renderGroups(), so every chip keeps this panel's action menus and
  // dialogs. Dialogs then dock to the bottom of the window because the chips can be far
  // above the panel's end. Without it the panel renders its usual document-level groups.
  chapterRenderer?: (renderGroups: (source: Partial<EntitiesByType> | null | undefined) => React.ReactNode) => React.ReactNode;
  // Bump to force a full reset + refetch for the same document (e.g. after the
  // editor reopened it, which deletes all derived entities server-side).
  refreshKey?: number;
  externalDisabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
  // Fires after a successful refresh/delete/merge/exclude — lets a host page
  // that keeps its own copy of this document's entities (e.g. read.tsx's
  // chapter-scoped sidebar) know it should refetch too.
  onEntitiesChanged?: () => void;
  // kraj-* tags (country_gazetteer + extract_countries_hybrid, LLM-vetted),
  // scoped by the caller (read.tsx passes the chapter- or document-level
  // list) — rendered as the first block, ahead of Osoby. When omitted, use
  // the document-level countries returned by GET /website_entities.
  countries?: CountryTag[];
}) => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [entities, setEntities] = React.useState<EntitiesByType | null>(null);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [isDetectingCountries, setIsDetectingCountries] = React.useState(false);
  const [fetchedCountries, setFetchedCountries] = React.useState<CountryTag[]>([]);
  const countries = providedCountries ?? fetchedCountries;
  const [enrichmentJob, setEnrichmentJob] = React.useState<EntityEnrichmentJob | null>(null);
  const [message, setMessage] = React.useState("");
  // Set when the last NER refresh found ner_service unreachable (backend:
  // web_documents.ner_unavailable_at) — lets us warn instead of implying
  // "no entities" when the real cause was a dead service.
  const [nerUnavailableAt, setNerUnavailableAt] = React.useState<string | null>(null);
  // miejsce-* tags of Document.tags (summary of verified places), read-only.
  const [placeTags, setPlaceTags] = React.useState<string[]>([]);
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
  // "Opis" flow (orgName): chip whose Organization.description is being edited
  const [orgDescriptionFor, setOrgDescriptionFor] = React.useState<EntityItem | null>(null);
  const [orgDescriptionText, setOrgDescriptionText] = React.useState("");
  const [orgDescriptionBusy, setOrgDescriptionBusy] = React.useState(false);
  const [orgPromptOpen, setOrgPromptOpen] = React.useState(false);
  const [orgPrompt, setOrgPrompt] = React.useState("");
  const [orgModels, setOrgModels] = React.useState<ModelOption[]>([]);
  // Arena: the same prompt through 2-4 models, proposals side by side (nothing stored).
  const [arenaOpen, setArenaOpen] = React.useState(false);
  const [arenaModels, setArenaModels] = React.useState<string[]>([]);
  const [arenaResults, setArenaResults] = React.useState<{
    model: string; label: string; result_status: string; description: string | null; latency_ms: number;
    tokens: number | null; cost: string | null; currency: string | null; error_code: string | null;
  }[]>([]);
  const [orgModel, setOrgModel] = React.useState("");
  const [orgDescriptionInfo, setOrgDescriptionInfo] = React.useState("");
  // "Wyklucz" flow: entity to suppress in future NER runs (ner_exclusions)
  const [excludeFor, setExcludeFor] = React.useState<{ item: EntityItem; entityType: string } | null>(null);
  const [deleteFor, setDeleteFor] = React.useState<EntityItem | null>(null);
  const [renameFor, setRenameFor] = React.useState<EntityItem | null>(null);
  const [renameText, setRenameText] = React.useState("");
  const [isRenaming, setIsRenaming] = React.useState(false);
  const [isSettingRelevance, setIsSettingRelevance] = React.useState(false);
  // "Zmień na miejsce" (person -> place) and "Podziel" (one place entity listing several places) forms.
  const [toPlaceFor, setToPlaceFor] = React.useState<EntityItem | null>(null);
  const [toPlaceText, setToPlaceText] = React.useState("");
  // "Zmień na organizację" for a person: the organization may be named differently than the mention ("Xie" -> "X").
  const [toOrgFor, setToOrgFor] = React.useState<EntityItem | null>(null);
  const [toOrgText, setToOrgText] = React.useState("");
  // "Połącz z inną osobą w dokumencie": two person rows of this document folded into one ("Stone" -> "Andy Stone").
  // `chapter` = the persons of the chapter the menu was opened in (the list starts there; a book has hundreds).
  const [personDocMergeFor, setPersonDocMergeFor] =
    React.useState<{ item: EntityItem; chapter?: EntityItem[] } | null>(null);
  // "Nadaj prawdziwe nazwisko": a nickname ("Łacha Piachu") is an alias of the person it names ("Icchak Herzog").
  // "To błąd transkrypcji": the mention is a speech-to-text slip of another entity of this document ("Hutni" -> "Huti").
  const [slipFor, setSlipFor] = React.useState<EntityItem | null>(null);
  const [slipText, setSlipText] = React.useState("");
  const [realNameFor, setRealNameFor] = React.useState<EntityItem | null>(null);
  const [realNameText, setRealNameText] = React.useState("");
  const [placeMergeQuery, setPlaceMergeQuery] = React.useState("");
  const [personMergeAll, setPersonMergeAll] = React.useState(false);
  const [personMergeQuery, setPersonMergeQuery] = React.useState("");
  // Floating action menu of a mention clicked in the host's text (see the mentionMenu prop).
  const [openMentionSub, setOpenMentionSub] = React.useState<string | null>(null);
  const mentionMenuRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!mentionMenu) return;
    setOpenMentionSub(null);
    const outside = (event: PointerEvent) => {
      if (!mentionMenuRef.current?.contains(event.target as Node)) onMentionMenuClose?.();
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onMentionMenuClose?.(); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [mentionMenu, onMentionMenuClose]);
  const [splitFor, setSplitFor] = React.useState<EntityItem | null>(null);
  const [splitKind, setSplitKind] = React.useState<"place" | "organization">("place");
  const [splitText, setSplitText] = React.useState("");
  const [isRetyping, setIsRetyping] = React.useState(false);
  const [wikiFor, setWikiFor] = React.useState<EntityItem | null>(null);
  const [wikiText, setWikiText] = React.useState("");
  // Confirmation step of every organization merge: side-by-side comparison + what will change.
  const [mergePreview, setMergePreview] = React.useState<{
    source: EntityItem;
    targetOrganizationId: number;
    targetEntityId?: number;
    data: MergePreviewData | null;
    error: string | null;
  } | null>(null);
  const [isMergingOrg, setIsMergingOrg] = React.useState(false);
  // "Dane źródła" flow: type / website / description of a cited source (information_sources).
  const [sourceDetailsFor, setSourceDetailsFor] = React.useState<EntityItem | null>(null);
  const [sourceType, setSourceType] = React.useState("");
  const [sourceDomain, setSourceDomain] = React.useState("");
  const [sourceDescription, setSourceDescription] = React.useState("");
  const [isSavingSource, setIsSavingSource] = React.useState(false);
  const [mergeHint, setMergeHint] = React.useState<{
    source: EntityItem; target: EntityItem; conflict: boolean;
  } | null>(null);
  const [isMergingPlace, setIsMergingPlace] = React.useState(false);
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
        setFetchedCountries(response.data.countries ?? []);
        setNerUnavailableAt(response.data.ner_unavailable_at ?? null);
        setPlaceTags(Array.isArray(response.data.place_tags) ? response.data.place_tags : []);
        onEntitiesChanged?.();
      })
      .catch((error) => {
        console.error("Error fetching entities", error);
        setMessage("Nie udało się pobrać encji.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, apiUrl, apiKey]);

  const sawActiveJobRef = React.useRef(false);

  const fetchEnrichmentJob = React.useCallback(() => {
    if (!docId) return;
    axios
      .get(`${apiUrl}/website_entities/enrichment_job`, { params: { id: docId }, headers })
      .then((response) => {
        const job = response.data.job ?? null;
        setEnrichmentJob(job);
        // Only announce completion of a job watched in this session. A stale
        // "done" record (e.g. from before the document was reopened for
        // editing) next to an empty list read as a contradiction.
        if (job?.status === "done" && sawActiveJobRef.current) {
          setMessage("Pełna weryfikacja encji zakończona.");
        }
      })
      .catch((error) => console.error("Error fetching entity enrichment job", error));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, apiUrl, apiKey]);

  React.useEffect(() => {
    sawActiveJobRef.current = false;
    setEntities(null);
    setPlaceTags([]);
    setFetchedCountries([]);
    setSourceDetailsFor(null);
    setMergePreview(null);
    setMessage("");
    setEditMode(false);
    setMergeFor(null);
    setOrgMergeFor(null);
    setPlaceMergeFor(null);
    setAliasFor(null);
    setOrgDescriptionFor(null);
    setExcludeFor(null);
    setDeleteFor(null);
    setRenameFor(null);
    setRenameText("");
    setMergeHint(null);
    setReviewReason("");
    setReviewComment("");
    fetchEntities();
    fetchEnrichmentJob();
  }, [docId, refreshKey, fetchEntities, fetchEnrichmentJob]);

  const enrichmentActive = enrichmentJob?.status === "queued"
    || enrichmentJob?.status === "running"
    || enrichmentJob?.status === "cancel_requested";

  React.useEffect(() => {
    if (enrichmentActive) sawActiveJobRef.current = true;
  }, [enrichmentActive]);

  React.useEffect(() => {
    if (!enrichmentActive) return undefined;
    const timer = window.setInterval(() => {
      fetchEnrichmentJob();
      fetchEntities();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [enrichmentActive, fetchEnrichmentJob, fetchEntities]);

  const handleDetectCountries = async () => {
    if (!docId) return;
    setIsDetectingCountries(true);
    onBusyChange?.(true);
    setMessage("");
    try {
      const response = await axios.post(
        `${apiUrl}/document/${docId}/countries/detect`, {}, { headers: jsonHeaders },
      );
      setFetchedCountries(response.data.countries);
      setMessage(response.data.added.length > 0
        ? `Dodano państw: ${response.data.added.length}.` : "Nie wykryto nowych państw.");
      onEntitiesChanged?.();
    } catch (error: any) {
      console.error("Error detecting countries", error);
      setMessage(`Nie udało się wykryć państw: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsDetectingCountries(false);
      onBusyChange?.(false);
    }
  };

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
      setEnrichmentJob(response.data.enrichment_job ?? null);
      setNerUnavailableAt(null);
      onEntitiesChanged?.();
      if (response.data.refreshed === 0) {
        setMessage("Nie wykryto żadnych osób ani miejsc w tym dokumencie.");
      } else {
        setMessage("Wykryto encje. Trwa ich pełna weryfikacja w tle.");
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

  const openMergePreview = async (sourceItem: EntityItem, targetOrganizationId: number, targetEntityId?: number) => {
    if (sourceItem.organization_id == null) return;
    setMergePreview({ source: sourceItem, targetOrganizationId, targetEntityId, data: null, error: null });
    try {
      const response = await axios.get(`${apiUrl}/organizations/${sourceItem.organization_id}/merge_preview`,
        { params: { target_id: targetOrganizationId }, headers });
      setMergePreview((current) => current && { ...current, data: response.data });
    } catch (error: any) {
      setMergePreview((current) => current && {
        ...current, error: error.response?.data?.message || "Nie udało się pobrać porównania organizacji.",
      });
    }
  };

  const confirmMergePreview = async () => {
    if (!mergePreview?.data || mergePreview.source.id == null || isMergingOrg) return;
    const { source, targetEntityId, targetOrganizationId, data } = mergePreview;
    setIsMergingOrg(true);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/document/${docId}/organizations/merge`, {
        source_entity_id: source.id,
        ...(targetEntityId != null ? { target_entity_id: targetEntityId } : { target_organization_id: targetOrganizationId }),
        make_global_alias: true,
      }, { headers: jsonHeaders });
      setMergePreview(null);
      setRenameFor(null);
      setOrgMergeFor(null);
      fetchEntities();
      setMessage(`Połączono organizacje: „${data.source.canonical_name}” → „${data.target.canonical_name}”.`);
    } catch (error: any) {
      setMessage(`Nie udało się połączyć organizacji: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsMergingOrg(false);
    }
  };

  // Renaming an organization is global (registry + every document entity + the cited
  // source bound to it); the backend keeps the old name as an alias and merges a
  // same-named duplicate source.
  const handleOrganizationRename = async () => {
    if (renameFor?.organization_id == null || !renameText.trim() || isRenaming) return;
    setIsRenaming(true);
    setMessage("");
    try {
      const response = await axios.patch(`${apiUrl}/organizations/${renameFor.organization_id}`,
        { canonical_name: renameText.trim() }, { headers: jsonHeaders });
      const rename = response.data.rename;
      setRenameFor(null);
      fetchEntities();
      const sourceNote = rename?.source?.action === "merged"
        ? " Źródło scalono z istniejącym wpisem o tej nazwie."
        : rename?.source?.action === "renamed" ? " Nazwa źródła zmieniona." : "";
      setMessage(`Nazwa organizacji poprawiona: „${rename?.old_name ?? renameFor.text}” → „${response.data.canonical_name}”.${sourceNote}`);
    } catch (error: any) {
      const status = error.response?.status;
      if (status === 404) {
        setRenameFor(null);
        fetchEntities();
        setMessage("Ta organizacja już nie istnieje. Odświeżono listę.");
      } else if (status === 409 && error.response?.data?.existing_organization_id != null) {
        // The name is taken: this is really a merge into that organization — show the comparison.
        const source = renameFor;
        setMessage(`Nazwa „${renameText.trim()}” należy już do innej organizacji (id ${error.response.data.existing_organization_id}). Sprawdź porównanie poniżej i potwierdź połączenie.`);
        setRenameFor(null);
        void openMergePreview(source, error.response.data.existing_organization_id);
      } else if (status === 409) {
        setMessage(`${error.response?.data?.message || "Taka nazwa już istnieje."} Użyj „Połącz z inną organizacją”.`);
      } else {
        // Everything needed to reproduce the failure: document, names before/after, and why.
        const reason = error.response
          ? `${error.response.data?.message || "brak komunikatu z serwera"} (HTTP ${status})`
          : `${error.message || "brak odpowiedzi serwera"} (brak odpowiedzi HTTP)`;
        setMessage(`Nie udało się poprawić nazwy organizacji. Dokument: ${docId}, organizacja: ${renameFor.organization_id}, `
          + `nazwa początkowa: „${renameFor.text}”, nazwa końcowa: „${renameText.trim()}”. Przyczyna: ${reason}`);
      }
    } finally {
      setIsRenaming(false);
    }
  };

  const handleSourceDetailsSubmit = async () => {
    if (sourceDetailsFor?.information_source_id == null || isSavingSource) return;
    setIsSavingSource(true);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/information_sources/${sourceDetailsFor.information_source_id}`, {
        source_type: sourceType.trim(),
        domain: sourceDomain.trim(),
        description: sourceDescription.trim(),
      }, { headers: jsonHeaders });
      setSourceDetailsFor(null);
      fetchEntities();
      setMessage("Dane źródła zapisane.");
    } catch (error: any) {
      if (error.response?.status === 404) {
        setSourceDetailsFor(null);
        fetchEntities();
        setMessage("To źródło już nie istnieje. Odświeżono listę.");
      } else {
        setMessage(error.response?.data?.message || "Nie udało się zapisać danych źródła.");
      }
    } finally {
      setIsSavingSource(false);
    }
  };

  const handleRelevanceChange = async (item: EntityItem, relevance: EntityRelevance) => {
    if (item.id == null || isSettingRelevance || externalDisabled) return;
    setIsSettingRelevance(true);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/website_entities/${item.id}/relevance`, { relevance }, { headers: jsonHeaders });
      fetchEntities();
      setMessage("Związek encji z tematem został zapisany.");
    } catch (error: unknown) {
      setMessage("Nie udało się zapisać związku encji z tematem.");
      if (axios.isAxiosError(error) && error.response?.status === 404) fetchEntities();
    } finally {
      setIsSettingRelevance(false);
    }
  };

  const handleRename = async () => {
    if (renameFor?.organization_id != null) {
      await handleOrganizationRename();
      return;
    }
    if (renameFor?.id == null || !renameText.trim() || isRenaming) return;
    setIsRenaming(true);
    setMergeHint(null);
    setMessage("");
    try {
      const response = await axios.patch(`${apiUrl}/website_entities/${renameFor.id}`,
        { text: renameText.trim() }, { headers: jsonHeaders });
      setRenameFor(null);
      fetchEntities();
      setMessage(`Nazwa miejsca została poprawiona — ${response.data.geocoded
        ? "miejsce potwierdzone przez geokoder" : "geokoder nie potwierdził"}.`);
      if (response.data.same_place_entity) {
        setMergeHint({ source: renameFor, target: response.data.same_place_entity, conflict: false });
      }
    } catch (error: any) {
      setMessage(error.response?.data?.message || "Nie udało się poprawić nazwy miejsca.");
      if (error.response?.status === 404) {
        // Stale list: the entity is gone (e.g. the document was reopened for
        // editing, which deletes its derived entities) — reload what exists.
        setRenameFor(null);
        fetchEntities();
        setMessage("Ta encja już nie istnieje (dokument mógł zostać otwarty do edycji lub encje wykryto ponownie). Odświeżono listę.");
      }
      if (error.response?.status === 409 && error.response.data.conflict_entity) {
        setMergeHint({ source: renameFor, target: error.response.data.conflict_entity, conflict: true });
      }
    } finally {
      setIsRenaming(false);
    }
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

  const approveOrganization = async (item: EntityItem) => {
    if (item.organization_link_id == null) return;
    try {
      await axios.post(`${apiUrl}/document/${docId}/organizations/${item.organization_link_id}/approve`, {}, { headers: jsonHeaders });
      fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się zatwierdzić organizacji: ${error.response?.data?.message || error.message}`);
    }
  };

  const mergePlaces = async (source: EntityItem | null, target: EntityItem) => {
    if (source?.id == null || target.id == null || isMergingPlace) {
      return;
    }
    setMessage("");
    setIsMergingPlace(true);
    try {
      await axios.post(
        `${apiUrl}/document/${docId}/places/merge`,
        { source_entity_id: source.id, target_entity_id: target.id },
        { headers: jsonHeaders },
      );
      setPlaceMergeFor(null);
      setMergeHint(null);
      setRenameFor(null);
      fetchEntities();
      setMessage("Miejsca zostały połączone.");
    } catch (error: any) {
      console.error("Error merging place", error);
      setMessage(`Nie udało się połączyć miejsc: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsMergingPlace(false);
    }
  };
  const handlePlaceMergePick = (target: EntityItem) => mergePlaces(placeMergeFor, target);

  const mergeDocumentPersons = async (source: EntityItem, target: EntityItem) => {
    if (source.id == null || target.id == null || isMergingPlace) return;
    setMessage("");
    setIsMergingPlace(true);
    try {
      await axios.post(`${apiUrl}/document/${docId}/persons/merge`,
        { source_entity_id: source.id, target_entity_id: target.id }, { headers: jsonHeaders });
      setPersonDocMergeFor(null);
      await fetchEntities();
      setMessage(`Osoby „${source.text}” i „${target.text}” zostały połączone.`);
    } catch (error: any) {
      setMessage(`Nie udało się połączyć osób: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsMergingPlace(false);
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

  const handleOrgDescriptionSubmit = async () => {
    if (!orgDescriptionFor?.organization_id) {
      return;
    }
    setMessage("");
    try {
      await axios.patch(
        `${apiUrl}/organizations/${orgDescriptionFor.organization_id}`,
        { description: orgDescriptionText.trim() },
        { headers: jsonHeaders },
      );
      setOrgDescriptionFor(null);
      setOrgDescriptionText("");
      fetchEntities();
    } catch (error: any) {
      console.error("Error updating organization description", error);
      setMessage(`Nie udało się zapisać opisu: ${error.response?.data?.message || error.message}`);
    }
  };

  // Bielik drafts the organization description from the chapter that mentions it most; nothing is
  // stored until the reviewer presses "Zapisz".
  // The prompt and the model are shown first (POST .../describe/preview, no LLM call) so the reviewer can
  // edit the prompt and pick the model before "Generuj" sends exactly that text.
  const handleOrgDescriptionSuggest = async () => {
    if (orgDescriptionFor?.id == null) return;
    setMessage("");
    setOrgDescriptionBusy(true);
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${orgDescriptionFor.id}/describe/preview`, {}, { headers: jsonHeaders });
      setOrgPrompt(response.data.prompt ?? "");
      setOrgModels(response.data.models ?? []);
      setOrgModel(response.data.default_model ?? response.data.models?.[0]?.id ?? "");
      setOrgPromptOpen(true);
    } catch (error: any) {
      setMessage(`Nie udało się przygotować promptu: ${error.response?.data?.message || error.message}`);
    } finally {
      setOrgDescriptionBusy(false);
    }
  };

  const handleArenaRun = async () => {
    if (orgDescriptionFor?.id == null) return;
    setMessage("");
    setArenaResults([]);
    setOrgDescriptionBusy(true);
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${orgDescriptionFor.id}/describe/arena`,
        { models: arenaModels, prompt: orgPrompt }, { headers: jsonHeaders });
      setArenaResults(response.data.results ?? []);
    } catch (error: any) {
      setMessage(`Arena nie powiodła się: ${error.response?.data?.message || error.message}`);
    } finally {
      setOrgDescriptionBusy(false);
    }
  };

  const toggleArenaModel = (id: string) => setArenaModels((current) =>
    current.includes(id) ? current.filter((item) => item !== id) : current.length < 4 ? [...current, id] : current);

  const handleOrgDescriptionGenerate = async () => {
    if (orgDescriptionFor?.id == null) return;
    setMessage("");
    setOrgDescriptionBusy(true);
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${orgDescriptionFor.id}/describe`,
        { model: orgModel || undefined, prompt: orgPrompt }, { headers: jsonHeaders });
      const data = response.data;
      if (data.result_status === "ok" && data.description) {
        setOrgDescriptionText(data.description);
        setOrgDescriptionInfo(`Propozycja: ${data.model}, ${data.latency_ms} ms`);
      } else if (data.result_status === "error") {
        setOrgDescriptionInfo("");
        setMessage(`Model ${data.model} nie odpowiedział: ${data.error_code ?? "błąd"}.`);
      } else {
        setOrgDescriptionInfo("");
        setMessage(`Model ${data.model} uznał, że rozdział nie wystarcza do opisu — wpisz go ręcznie.`);
      }
    } catch (error: any) {
      setMessage(`Nie udało się wygenerować opisu: ${error.response?.data?.message || error.message}`);
    } finally {
      setOrgDescriptionBusy(false);
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

  const [confirmingPlace, setConfirmingPlace] = React.useState<number | null>(null);
  const confirmPlace = async (item: EntityItem) => {
    if (item.id == null) return;
    setConfirmingPlace(item.id);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/website_entities/${item.id}/confirm_place`,
        { selected_geocode_id: item.proposed_geocode_id }, { headers: jsonHeaders });
      await fetchEntities();
    } catch {
      setMessage("Nie udało się zatwierdzić lokalizacji.");
    } finally {
      setConfirmingPlace(null);
    }
  };

  const rejectPlace = async (item: EntityItem) => {
    if (item.id == null) return;
    setConfirmingPlace(item.id);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/website_entities/${item.id}/reject_place`, {}, { headers: jsonHeaders });
      setMessage(`Propozycja lokalizacji dla „${item.text}” odrzucona — miejsce zostaje bez lokalizacji.`);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się odrzucić propozycji: ${error.response?.data?.message || error.message}`);
    } finally {
      setConfirmingPlace(null);
    }
  };

  const changePlaceToOrganization = async (item: EntityItem) => {
    if (item.id == null) return;
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${item.id}/to_organization`, {},
        { headers: jsonHeaders });
      setMessage(`„${item.text}” zmienione na organizację: ${response.data.organization_name}.`);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się zmienić na organizację: ${error.response?.data?.message || error.message}`);
    }
  };

  const changeOrganizationToPerson = async (item: EntityItem) => {
    if (item.id == null) return;
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${item.id}/to_person`, {},
        { headers: jsonHeaders });
      const linked = response.data.linked?.[0];
      setMessage(`„${item.text}” zmienione na osobę${linked ? `: ${linked}` : " (bez dopasowania w rejestrze osób)"}.`);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się zmienić na osobę: ${error.response?.data?.message || error.message}`);
    }
  };

  const changePersonToPlace = async () => {
    if (toPlaceFor?.id == null || !toPlaceText.trim()) return;
    setIsRetyping(true);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${toPlaceFor.id}/to_place`,
        { text: toPlaceText.trim() }, { headers: jsonHeaders });
      setMessage(`„${toPlaceFor.text}” zmienione na miejsce: ${response.data.place_name}.`);
      setToPlaceFor(null);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się zmienić na miejsce: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsRetyping(false);
    }
  };

  const changePersonToOrganization = async () => {
    if (toOrgFor?.id == null || !toOrgText.trim()) return;
    setIsRetyping(true);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${toOrgFor.id}/to_organization`,
        { text: toOrgText.trim() }, { headers: jsonHeaders });
      setMessage(`„${toOrgFor.text}” zmienione na organizację: ${response.data.organization_name}.`);
      setToOrgFor(null);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się zmienić na organizację: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsRetyping(false);
    }
  };

  const markTranscriptionError = async () => {
    if (slipFor?.id == null || !slipText.trim()) return;
    setIsRetyping(true);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${slipFor.id}/transcription_error`,
        { correct_name: slipText.trim() }, { headers: jsonHeaders });
      setMessage(`„${slipFor.text}” oznaczone jako błąd transkrypcji „${response.data.entity_text}”${
        response.data.glossary ? " (dopisane do słownika kanału)" : ""}.`);
      setSlipFor(null);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się oznaczyć błędu transkrypcji: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsRetyping(false);
    }
  };

  const assignRealName = async () => {
    if (realNameFor?.id == null || !realNameText.trim()) return;
    setIsRetyping(true);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${realNameFor.id}/real_name`,
        { name: realNameText.trim() }, { headers: jsonHeaders });
      setMessage(`„${realNameFor.text}” to ${response.data.canonical_name}${response.data.created ? " (nowa osoba w rejestrze)" : ""}.`);
      setRealNameFor(null);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się nadać nazwiska: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsRetyping(false);
    }
  };

  const savePlaceWikipedia = async () => {
    if (!wikiFor) return;
    setIsRetyping(true);
    setMessage("");
    try {
      await axios.put(`${apiUrl}/places/profile`,
        { name: wikiFor.text, wikipedia_url: wikiText.trim() || null }, { headers: jsonHeaders });
      setMessage(wikiText.trim() ? `Zapisano artykuł Wikipedii dla „${wikiFor.text}”.` : `Usunięto link Wikipedii dla „${wikiFor.text}”.`);
      setWikiFor(null);
      await fetchEntities();
    } catch (error: any) {
      setMessage(`Nie udało się zapisać linku Wikipedii: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsRetyping(false);
    }
  };

  const splitParts = splitText.split(/[,;]+/).map((part) => part.trim()).filter(Boolean);
  const splitEntity = async () => {
    if (splitFor?.id == null || splitParts.length < 2) return;
    const endpoint = splitKind === "organization" ? "split_organization" : "split_place";
    setIsRetyping(true);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/website_entities/${splitFor.id}/${endpoint}`,
        { parts: splitParts }, { headers: jsonHeaders });
      setMessage(`„${splitFor.text}” podzielone na: ${response.data.parts.join(", ")}.`);
      setSplitFor(null);
      await fetchEntities();
    } catch (error: any) {
      const what = splitKind === "organization" ? "organizacji" : "miejsca";
      setMessage(`Nie udało się podzielić ${what}: ${error.response?.data?.message || error.message}`);
    } finally {
      setIsRetyping(false);
    }
  };

  if (!docId) {
    return null;
  }

  const persons = entities?.persName ?? [];
  // A country mention NER tags as orgName (e.g. "Arabią Saudyjską" in a
  // "rząd Arabii Saudyjskiej" phrase) is dropped here — it belongs in the
  // "Państwa" block below, not Organizacje.
  const organizations = (entities?.orgName ?? []).filter((item) => !item.is_country);
  const citedSources = organizations.filter((item) => item.information_source_id != null);
  const otherOrganizations = organizations.filter((item) => item.information_source_id == null);
  // The UI combines both NER place categories into one section, while an
  // exclusion must preserve the category that produced each chip. Country
  // mentions (is_country) are dropped the same way as for orgName above —
  // the "Państwa" block covers them with LLM-vetted kraj-* tags instead of
  // an ungeocoded, permanently-unverified NER chip.
  const allPlaces = [
    ...(entities?.geogName ?? []).map((item) => ({ ...item, entity_type: "geogName" as const })),
    ...(entities?.placeName ?? []).map((item) => ({ ...item, entity_type: "placeName" as const })),
  ];
  const rejectedPlaces = allPlaces.filter(item => item.place_verification_status === "rejected");
  const places = allPlaces.filter(item => !item.is_country && item.place_verification_status !== "rejected");
  const facilities = entities?.facility ?? [];
  const isEmpty = !persons.length && !organizations.length && !places.length && !rejectedPlaces.length
    && !facilities.length && !countries.length;
  const reviewFormValid = Boolean(reviewReason)
    && (reviewReason !== "other" || Boolean(reviewComment.trim()));

  const resetFlows = () => {
    setMergeHint(null);
    setRenameFor(null);
    setToPlaceFor(null);
    setToOrgFor(null);
    setPersonDocMergeFor(null);
    setRealNameFor(null);
    setSlipFor(null);
    setMergeFor(null);
    setSplitFor(null);
    setWikiFor(null);
    setDeleteFor(null);
    setExcludeFor(null);
    setMergeFor(null);
    setOrgMergeFor(null);
    setPlaceMergeFor(null);
    setAliasFor(null);
    setOrgDescriptionFor(null);
    setSourceDetailsFor(null);
    setSplitFor(null);
    setMergePreview(null);
    setReviewReason("");
    setReviewComment("");
  };
  const showInTextEntry = (item: EntityItem, kind: "persName" | "orgName" | "place"): MenuEntry[] =>
    onShowInText ? [{ label: "🔎 Podświetl w tekście", action: () => onShowInText(item, kind) }] : [];

  // A speech-to-text slip of another entity of this document: no registry change, no alias of a person name.
  const slipEntry = (item: EntityItem): MenuEntry => ({
    label: "To błąd transkrypcji…", action: () => { resetFlows(); setSlipFor(item); setSlipText(""); },
  });

  const organizationMenuActions = (item: EntityItem): MenuEntry[] => {
    if (item.id == null) return [];
    const entries: MenuEntry[] = [...showInTextEntry(item, "orgName")];
    if (item.information_source_id != null) {
      entries.push({ label: "Otwórz w rejestrze źródeł", to: `/information-sources?id=${item.information_source_id}` });
    } else if (item.organization_id != null) {
      entries.push({ label: "Otwórz w rejestrze organizacji", to: `/organizations/${item.organization_id}` });
    }
    if (item.organization_id != null) {
      entries.push({ label: "Popraw nazwę", action: () => { resetFlows(); setRenameFor(item); setRenameText(item.text); } });
    }
    if (item.information_source_id != null) {
      entries.push({ label: "Dane źródła (typ, strona, opis)", action: () => {
        resetFlows();
        setSourceDetailsFor(item);
        setSourceType(item.information_source_type ?? "");
        setSourceDomain(item.information_source_domain ?? "");
        setSourceDescription(item.information_source_description ?? item.organization_description ?? "");
      } });
    } else if (item.organization_id != null) {
      entries.push({ label: "Opis organizacji", action: () => {
        resetFlows();
        setOrgDescriptionFor(item);
        setOrgDescriptionText(item.organization_description ?? "");
        setOrgPromptOpen(false);
        setOrgDescriptionInfo("");
      } });
    }
    if (item.organization_id != null) {
      entries.push({ label: "Połącz z inną organizacją", action: () => {
        resetFlows();
        setOrgMergeFor(item);
        setOrgSearchQ("");
        setOrgSearchResults([]);
      } });
    }
    // Two glued mentions ("NATO Moskwa"): a two-word name is only offered as a pre-filled split, never applied.
    const words = item.text.trim().split(/\s+/);
    const orgSuggestion = words.length === 2 ? words : null;
    entries.push({
      label: orgSuggestion ? `Podziel na: ${orgSuggestion.join(", ")}` : "Podziel na kilka organizacji…",
      action: () => {
        resetFlows(); setSplitKind("organization"); setSplitFor(item); setSplitText(orgSuggestion?.join(", ") ?? item.text);
      },
    });
    // NER mislabel: a place ("Tela Avivwu") or a person tagged as an organization.
    entries.push(slipEntry(item));
    entries.push({ label: "Zmień na miejsce", action: () => { resetFlows(); setToPlaceFor(item); setToPlaceText(item.text); } });
    entries.push({ label: "Zmień na osobę", action: () => { resetFlows(); void changeOrganizationToPerson(item); } });
    entries.push({ label: "× Usuń encję", action: () => { resetFlows(); setDeleteFor(item); } });
    entries.push({ label: "🚫 Usuń i nie wykrywaj więcej", action: () => {
      resetFlows(); setExcludeFor({ item, entityType: "orgName" });
    } });
    return entries;
  };
  const relevanceEntries = (item: EntityItem): MenuEntry[] => [{
    label: `Związek z tematem: ${RELEVANCE_OPTIONS.find((option) => option.value === (item.relevance ?? "central"))?.label}`,
    children: RELEVANCE_OPTIONS.map((option) => ({
      label: `${(item.relevance ?? "central") === option.value ? "✓" : "○"} ${option.label}`,
      action: () => void handleRelevanceChange(item, option.value),
    })),
  }];
  const personMenuActions = (item: EntityItem, chapterPersons?: EntityItem[]): MenuEntry[] => item.id == null ? [] : [
    ...showInTextEntry(item, "persName"),
    ...relevanceEntries(item),
    // A nickname ("Łacha Piachu") or a mishearing: name the real person, or point the mention at a registry person.
    slipEntry(item),
    { label: "Nadaj prawdziwe nazwisko…", action: () => { resetFlows(); setRealNameFor(item); setRealNameText(item.canonical_name ?? ""); } },
    ...(item.link_id != null ? [{ label: "To inna osoba z rejestru…", action: () => {
      resetFlows(); setMergeFor(item); setSearchQ(""); setSearchResults([]);
    } }] : []),
    { label: "Otwórz osobę w rejestrze (nowa karta, edycja)", to: item.person_id != null
      ? `/persons/${item.person_id}` : `/persons?q=${encodeURIComponent(item.text)}`, newTab: true },
    { label: "Zmień na miejsce", action: () => { resetFlows(); setToPlaceFor(item); setToPlaceText(item.text); } },
    ...(persons.some((person) => person.id != null && person.id !== item.id)
      ? [{ label: "Połącz z inną osobą w dokumencie…", action: () => {
        resetFlows(); setPersonMergeAll(false); setPersonMergeQuery("");
        setPersonDocMergeFor({ item, chapter: chapterPersons });
      } }] : []),
    { label: "Zmień na organizację", action: () => { resetFlows(); setToOrgFor(item); setToOrgText(item.text); } },
    { label: "× Usuń encję", action: () => { resetFlows(); setDeleteFor(item); } },
    // A transcription slip ("egzekwo" heard as "Egekwo") or any other non-person: delete + never detect again.
    { label: "🚫 To nie jest osoba", action: () => {
      resetFlows(); setExcludeFor({ item, entityType: "persName" }); setReviewReason("not_a_person");
    } },
  ];
  const placeMenuActions = (item: EntityItem): MenuEntry[] => item.id == null ? [] : [
    ...showInTextEntry(item, "place"),
    ...relevanceEntries(item),
    { label: "Popraw nazwę", action: () => { resetFlows(); setRenameFor(item); setRenameText(item.text); } },
    ...(places.some((place) => place.id != null && place.id !== item.id)
      ? [{ label: "Połącz z innym miejscem", action: () => { resetFlows(); setPlaceMergeQuery(""); setPlaceMergeFor(item); } }] : []),
    { label: item.split_suggestion ? `Podziel na: ${item.split_suggestion.join(", ")}` : "Podziel na kilka miejsc…",
      action: () => {
        resetFlows(); setSplitKind("place"); setSplitFor(item); setSplitText(item.split_suggestion?.join(", ") ?? item.text);
      } },
    { label: item.wikipedia_url ? "Zmień stronę Wikipedii" : "Dodaj stronę Wikipedii",
      action: () => { resetFlows(); setWikiFor(item); setWikiText(item.wikipedia_url ?? ""); } },
    { label: "Otwórz w rejestrze miejsc", to: `/places?name=${encodeURIComponent(item.text)}` },
    slipEntry(item),
    { label: "Zmień na organizację", action: () => { resetFlows(); void changePlaceToOrganization(item); } },
    { label: "× Usuń encję", action: () => { resetFlows(); setDeleteFor(item); } },
    { label: "🚫 Usuń i nie wykrywaj więcej", action: () => {
      resetFlows(); setExcludeFor({ item, entityType: item.entity_type! });
    } },
  ];

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
          setRenameFor(null); setDeleteFor(item);
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
          // The places section combines geogName and placeName visually.
          // Use the item type there; '*' is only appropriate when explicitly
          // requested, never as a side effect of that presentation grouping.
          setRenameFor(null); setExcludeFor({ item, entityType: item.entity_type ?? entityType });
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
          onClick={() => { setRenameFor(null); setMergeFor(item); setAliasFor(null); setSearchQ(""); setSearchResults([]); }}
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
            setRenameFor(null); setOrgMergeFor(item);
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
      {entityType === "orgName" && item.organization_id != null && (
        <button
          type="button"
          style={{ ...chipActionStyle, color: "#667" }}
          title="Dodaj/edytuj krótki opis (widoczny jako podpowiedź w czytniku)"
          onClick={() => {
            setRenameFor(null); setOrgDescriptionFor(item);
            setOrgDescriptionText(item.organization_description ?? "");
            setDeleteFor(null);
            setExcludeFor(null);
            setMergeFor(null);
            setOrgMergeFor(null);
            setPlaceMergeFor(null);
            setAliasFor(null);
          }}
        >
          ℹ️
        </button>
      )}
      {entityType === "orgName" && item.organization_link_id != null && (
        item.organization_review_status === "approved"
          ? <span title="Zatwierdzone — NER nie usunie powiązania" style={{ color: "#15803d", marginLeft: 3 }}>✓</span>
          : <button type="button" style={{ ...chipActionStyle, color: "#15803d" }} title="Zatwierdź — chroń przed odświeżeniem NER" onClick={() => void approveOrganization(item)}>✓</button>
      )}
      {entityType === "orgName" && item.id != null && places.length > 0 && (
        <button
          type="button"
          style={{ ...chipActionStyle, color: "#1d5ca8" }}
          title="To nie organizacja, tylko miejsce — połącz z miejscem w tym dokumencie"
          onClick={() => {
            setRenameFor(null); setPlaceMergeFor(item);
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
            setRenameFor(null); setPlaceMergeFor(item);
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
          onClick={() => { setRenameFor(null); setAliasFor(item); setMergeFor(null); setAliasText(""); }}
        >
          +
        </button>
      )}
    </>
  );

  // Same grouping, filters and actions as the document-level chips below, applied to any
  // subset of entities (chapter mode). Items keep their ids, so every action still acts on
  // the document's entity rows.
  const renderGroups = (source: Partial<EntitiesByType> | null | undefined) => {
    const scopedOrganizations = (source?.orgName ?? []).filter((item) => !item.is_country);
    const scopedPlaces = [
      ...(source?.geogName ?? []).map((item) => ({ ...item, entity_type: "geogName" as const })),
      ...(source?.placeName ?? []).map((item) => ({ ...item, entity_type: "placeName" as const })),
    ].filter((item) => !item.is_country && item.place_verification_status !== "rejected");
    return (
      <>
        <EntityChips label={"Osoby"} items={source?.persName ?? []}
          menuActions={(item) => personMenuActions(item, source?.persName)}
          actions={editMode ? editActions("persName") : undefined} />
        <EntityChips label={"Źródła cytowane"} items={scopedOrganizations.filter((item) => item.information_source_id != null)}
          linkInformationSources menuActions={organizationMenuActions}
          actions={editMode ? editActions("orgName") : undefined} />
        <EntityChips label={"Organizacje"} items={scopedOrganizations.filter((item) => item.information_source_id == null)}
          linkOrganizations menuActions={organizationMenuActions}
          actions={editMode ? editActions("orgName") : undefined} />
        <EntityChips label={"Miejsca"} items={scopedPlaces} menuActions={placeMenuActions}
          actions={(item) => <>
            {item.place_verification_status === "needs_review" && item.proposed_geocode_id != null
              && item.proposed_lat != null && item.proposed_lon != null && (
              <button type="button" className="button" disabled={confirmingPlace !== null}
                onClick={() => void confirmPlace(item)}>Zatwierdź tę lokalizację</button>
            )}
            {item.place_verification_status === "needs_review" && (
              <button type="button" className="button" disabled={confirmingPlace !== null}
                onClick={() => void rejectPlace(item)}>Odrzuć propozycję</button>
            )}
            {editMode && editActions("placeName")(item)}
          </>} />
      </>
    );
  };

  const mentionEntries: MenuEntry[] = !mentionMenu ? [] : [
    { label: "Kopiuj nazwę", action: () => void copyText(mentionMenu.item.text) },
    ...(mentionMenu.kind === "persName" ? personMenuActions(mentionMenu.item, mentionMenu.chapterPersons)
      : mentionMenu.kind === "orgName" ? organizationMenuActions(mentionMenu.item)
        : placeMenuActions(mentionMenu.item)),
  ];
  const mentionItemStyle: React.CSSProperties = { display: "block", width: "100%", textAlign: "left",
    padding: "6px 8px", boxSizing: "border-box", background: "transparent", border: 0, cursor: "pointer" };

  return (
    <div style={{ marginTop: "10px", padding: "8px", border: "1px solid #ddd", borderRadius: "6px" }}>
      {mentionMenu && mentionEntries.length > 0 && (
        <div role="menu" ref={mentionMenuRef} aria-label={`Działania: ${mentionMenu.item.text}`}
          style={{ position: "fixed", zIndex: 30, minWidth: 230, maxWidth: "calc(100vw - 16px)", maxHeight: "70vh",
            overflowY: "auto", padding: 4, background: "white", border: "1px solid #b9c8de", borderRadius: 6,
            boxShadow: "0 2px 8px #0003",
            left: Math.max(8, Math.min(mentionMenu.x, window.innerWidth - 250)),
            top: Math.max(8, Math.min(mentionMenu.y, window.innerHeight - 320)) }}>
          <div style={{ padding: "2px 8px", fontSize: "0.8em", color: "#667" }}>{mentionMenu.item.text}</div>
          {mentionEntries.map((entry) => {
            if (entry.to && entry.newTab) {
              return (
                <a key={entry.label} role="menuitem" href={entry.to} target="_blank" rel="noopener noreferrer"
                  onClick={() => onMentionMenuClose?.()} style={{ ...mentionItemStyle, color: "inherit", textDecoration: "none" }}>
                  {entry.label}
                </a>
              );
            }
            if (entry.to) {
              return (
                <Link key={entry.label} role="menuitem" to={entry.to} onClick={() => onMentionMenuClose?.()}
                  style={{ ...mentionItemStyle, color: "inherit", textDecoration: "none" }}>{entry.label}</Link>
              );
            }
            if (entry.children) {
              const subOpen = openMentionSub === entry.label;
              return (
                <React.Fragment key={entry.label}>
                  <button type="button" role="menuitem" aria-expanded={subOpen} style={mentionItemStyle}
                    onClick={() => setOpenMentionSub(subOpen ? null : entry.label)}>
                    {entry.label} {subOpen ? "▾" : "▸"}
                  </button>
                  {subOpen && entry.children.map((child) => (
                    <button key={child.label} type="button" role="menuitem" style={{ ...mentionItemStyle, paddingLeft: 24 }}
                      onClick={() => { onMentionMenuClose?.(); child.action?.(); }}>{child.label}</button>
                  ))}
                </React.Fragment>
              );
            }
            return (
              <button key={entry.label} type="button" role="menuitem" style={mentionItemStyle}
                onClick={() => { onMentionMenuClose?.(); entry.action?.(); }}>{entry.label}</button>
            );
          })}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <strong>Osoby, miejsca i obiekty (NER)</strong>
        <button className={"button"} type="button" disabled={isRefreshing || isDetectingCountries || enrichmentActive || externalDisabled} onClick={handleRefresh}>
          {isRefreshing ? "Wykrywam..." : "Wykryj osoby, miejsca i obiekty"}
        </button>
        <button className={"button"} type="button"
          disabled={isRefreshing || isDetectingCountries || enrichmentActive || externalDisabled}
          onClick={handleDetectCountries}>
          {isDetectingCountries ? "Wykrywam państwa..." : "Wykryj państwa"}
        </button>
        {!isEmpty && (
          <button className={"button"} type="button" onClick={() => { setRenameFor(null); setEditMode(!editMode); setMergeFor(null); setOrgMergeFor(null); setPlaceMergeFor(null); setAliasFor(null); setExcludeFor(null); setDeleteFor(null); }}>
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
      {enrichmentActive && (
        <div style={{ marginTop: 8, color: "#667", fontSize: "0.9em" }}>
          Pełna weryfikacja encji trwa
          {Object.values(enrichmentJob?.progress?.stages ?? {}).length > 0
            ? ` — ${Object.values(enrichmentJob?.progress?.stages ?? {})
              .filter((stage) => stage.label !== "Gotowe")
              .map((stage) => `${stage.label}: ${stage.current} z ${stage.total}`)
              .join(" · ")}`
            : ""}.
          Wyniki odświeżą się automatycznie.
        </div>
      )}
      {enrichmentJob?.status === "failed" && (
        <div style={{ marginTop: 8, color: "#a33", fontSize: "0.9em" }}>
          Pełna weryfikacja encji nie powiodła się: {enrichmentJob.error || "nieznany błąd"}. Kliknij ponownie, aby spróbować jeszcze raz.
        </div>
      )}
      {countries.length > 0 && (
        <div style={{ marginTop: "6px" }}>
          <strong>Państwa:</strong>{" "}
          {[...countries].sort((a, b) => a.name_pl.localeCompare(b.name_pl, "pl")).map((country) => (
            <span key={country.slug} style={chipStyle}>{country.name_pl}</span>
          ))}
        </div>
      )}
      {chapterRenderer ? chapterRenderer(renderGroups) : <>
      <EntityChips label={"Osoby"} items={persons} menuActions={personMenuActions}
        actions={editMode ? editActions("persName") : undefined} />
      <EntityChips
        label={"Źródła cytowane"}
        items={citedSources}
        linkInformationSources
        menuActions={organizationMenuActions}
        actions={editMode ? editActions("orgName") : undefined}
      />
      <EntityChips
        label={"Organizacje"}
        items={otherOrganizations}
        linkOrganizations
        menuActions={organizationMenuActions}
        actions={editMode ? editActions("orgName") : undefined}
      />
      <EntityChips label={"Miejsca"} items={places} menuActions={placeMenuActions}
        actions={(item) => <>
          {item.place_verification_status === "needs_review" && item.proposed_geocode_id != null
            && item.proposed_lat != null && item.proposed_lon != null && (
            <button type="button" className="button" disabled={confirmingPlace !== null}
              onClick={() => void confirmPlace(item)}>Zatwierdź tę lokalizację</button>
          )}
          {item.place_verification_status === "needs_review" && (
            <button type="button" className="button" disabled={confirmingPlace !== null}
              onClick={() => void rejectPlace(item)}>Odrzuć propozycję</button>
          )}
          {editMode && editActions("placeName")(item)}
        </>} />
      <RejectedPlaces key={docId} docId={docId} items={rejectedPlaces} />
      {placeTags.length > 0 && (
        <div style={{ marginTop: 4, fontSize: "0.85em", color: "#667" }}>
          Tagi miejsc: {placeTags.join(", ")}
          <InfoTip label="Czym są tagi miejsc">
            <strong>Tagi miejsc (miejsce-…)</strong> to podsumowanie miejsc potwierdzonych w tym dokumencie,
            zapisane w tagach dokumentu. Tu tylko do odczytu.
            <br /><br />
            <strong>Jak powstają:</strong> po wykryciu encji worker geokoduje miejsca, a model językowy wybiera
            te, które dokument faktycznie omawia. Nazwa kanoniczna z geokodera staje się tagiem. „Popraw nazwę”
            geokoduje poprawioną nazwę i dopisuje jej tag. Tag znika przy usunięciu ostatniej encji tego
            miejsca oraz przy otwarciu dokumentu do edycji.
            <br /><br />
            <strong>Gdzie są używane:</strong> w wyszukiwarce tagi są częścią przeszukiwanego tekstu dokumentu
            (dopasowanie tekstowe i ocena trafności); nie ma osobnego filtra po tagach. Widać je też w polu
            tagów edytora i w czytniku. Mapa ich nie używa: kraje bierze z tagów kraj-…, a punkty
            ze współrzędnych encji.
            <br /><br />
            <strong>Inne tagi:</strong> tematyczne (np. geopolityka, wojsko), nadawane przez model; kraj-…
            (omawiane państwa); tagi z notatek Obsidiana (np. wiedza-…) i własne. Pytania kontrolne są dobierane
            po zgodności tagów dokumentu z tagami pytań.
          </InfoTip>
        </div>
      )}
      <EntityChips label={"Obiekty infrastruktury"} items={facilities} />
      </>}

      <div style={chapterRenderer ? { position: "sticky", bottom: 0, zIndex: 5, maxHeight: "50vh", overflowY: "auto" } : undefined}>
      {mergeHint && (
        <div style={{ marginTop: 8 }}>
          <span>{mergeHint.conflict
            ? `Miejsce „${mergeHint.target.text}” już istnieje — połączyć?`
            : `To samo miejsce co „${mergeHint.target.text}” — połączyć?`}</span>
          <button type="button" disabled={isMergingPlace}
            onClick={() => void mergePlaces(mergeHint.source, mergeHint.target)}>Połącz</button>
          <button type="button" disabled={isMergingPlace} onClick={() => setMergeHint(null)}>Nie</button>
        </div>
      )}
      {renameFor && (
        <div onKeyDown={(event) => {
          if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
            event.preventDefault(); event.stopPropagation(); void handleRename();
          }
        }}
          style={{ marginTop: 8, padding: 8, background: "#eef4ff", borderRadius: 6 }}>
          <label>{renameFor.organization_id != null ? "Popraw nazwę organizacji" : "Popraw nazwę miejsca"}
            <input autoFocus value={renameText} maxLength={500} disabled={isRenaming}
              onChange={(event) => setRenameText(event.target.value)} />
          </label>
          {renameFor.organization_id != null && (
            <div style={{ color: "#667", fontSize: "0.85em" }}>
              Zmiana jest globalna: dotyczy rejestru organizacji, tego i innych dokumentów oraz powiązanego
              źródła. Stara nazwa zostaje aliasem.
            </div>
          )}
          <button type="button" className="button" disabled={isRenaming || !renameText.trim()}
            onClick={() => void handleRename()}>Zatwierdź</button>
          <button type="button" disabled={isRenaming} onClick={() => setRenameFor(null)}>Anuluj</button>
        </div>
      )}

      {toOrgFor && (
        <div onKeyDown={(event) => {
          if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
            event.preventDefault(); event.stopPropagation(); void changePersonToOrganization();
          }
        }}
          style={{ marginTop: 8, padding: 8, background: "#eef4ff", borderRadius: 6 }}>
          <label>Nazwa organizacji (zamiast „{toOrgFor.text}”)
            <input autoFocus value={toOrgText} maxLength={500} disabled={isRetyping}
              onChange={(event) => setToOrgText(event.target.value)} />
          </label>
          <button type="button" className="button" disabled={isRetyping || !toOrgText.trim()}
            onClick={() => void changePersonToOrganization()}>Zmień na organizację</button>
          <button type="button" disabled={isRetyping} onClick={() => setToOrgFor(null)}>Anuluj</button>
        </div>
      )}

      {toPlaceFor && (
        <div onKeyDown={(event) => {
          if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
            event.preventDefault(); event.stopPropagation(); void changePersonToPlace();
          }
        }}
          style={{ marginTop: 8, padding: 8, background: "#eef4ff", borderRadius: 6 }}>
          <label>Nazwa miejsca (zamiast „{toPlaceFor.text}”)
            <input autoFocus value={toPlaceText} maxLength={500} disabled={isRetyping}
              onChange={(event) => setToPlaceText(event.target.value)} />
          </label>
          <button type="button" className="button" disabled={isRetyping || !toPlaceText.trim()}
            onClick={() => void changePersonToPlace()}>Zmień na miejsce</button>
          <button type="button" disabled={isRetyping} onClick={() => setToPlaceFor(null)}>Anuluj</button>
        </div>
      )}

      {wikiFor && (
        <div onKeyDown={(event) => {
          if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
            event.preventDefault(); event.stopPropagation(); void savePlaceWikipedia();
          }
        }}
          style={{ marginTop: 8, padding: 8, background: "#eef4ff", borderRadius: 6 }}>
          <label>Artykuł Wikipedii dla „{wikiFor.text}”
            <input autoFocus value={wikiText} maxLength={500} disabled={isRetyping} placeholder="https://pl.wikipedia.org/wiki/…"
              onChange={(event) => setWikiText(event.target.value)} />
          </label>
          <div style={{ color: "#667", fontSize: "0.85em" }}>
            Link zapisuje się globalnie dla miejsca (dotyczy też innych dokumentów). Pusty adres usuwa link.
          </div>
          <button type="button" className="button" disabled={isRetyping || (!wikiText.trim() && !wikiFor.wikipedia_url)}
            onClick={() => void savePlaceWikipedia()}>Zapisz</button>
          <button type="button" disabled={isRetyping} onClick={() => setWikiFor(null)}>Anuluj</button>
        </div>
      )}

      {splitFor && (
        <div onKeyDown={(event) => {
          if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
            event.preventDefault(); event.stopPropagation(); void splitEntity();
          }
        }}
          style={{ marginTop: 8, padding: 8, background: "#eef4ff", borderRadius: 6 }}>
          <label>Podziel „{splitFor.text}” na (nazwy oddzielone przecinkami)
            <input autoFocus value={splitText} maxLength={500} disabled={isRetyping}
              onChange={(event) => setSplitText(event.target.value)} />
          </label>
          <div style={{ color: "#667", fontSize: "0.85em" }}>
            {splitKind === "organization"
              ? "Każda część to osobna organizacja z rejestru (nowa, jeśli jeszcze jej nie ma); wystąpienia w tekście zostają przypisane."
              : "Każda część to osobne miejsce (państwo trafia do „Państw”); wystąpienia w tekście zostają przypisane."}
          </div>
          <button type="button" className="button" disabled={isRetyping || splitParts.length < 2}
            onClick={() => void splitEntity()}>Podziel</button>
          <button type="button" disabled={isRetyping} onClick={() => setSplitFor(null)}>Anuluj</button>
        </div>
      )}

      {deleteFor && (
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

      {excludeFor && (
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

      {slipFor && (
        <div onKeyDown={(event) => {
          if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
            event.preventDefault(); event.stopPropagation(); void markTranscriptionError();
          }
        }}
          style={{ marginTop: 8, padding: 8, background: "#eef4ff", borderRadius: 6 }}>
          <label>„{slipFor.text}” to błąd transkrypcji nazwy (encja już występująca w dokumencie, bez aliasu w rejestrze)
            <input autoFocus value={slipText} maxLength={500} disabled={isRetyping} list="slip-targets"
              placeholder="Poprawna nazwa, np. Huti" onChange={(event) => setSlipText(event.target.value)} />
          </label>
          <datalist id="slip-targets">
            {[...persons, ...organizations, ...allPlaces, ...(entities?.orgName ?? []).filter((o) => o.is_country)]
              .filter((candidate) => candidate.id !== slipFor.id)
              .map((candidate) => <option key={`${candidate.entity_type ?? ""}${candidate.id}`} value={candidate.text} />)}
          </datalist>
          <button type="button" className="button" disabled={isRetyping || !slipText.trim()}
            onClick={() => void markTranscriptionError()}>Oznacz</button>
          <button type="button" disabled={isRetyping} onClick={() => setSlipFor(null)}>Anuluj</button>
        </div>
      )}

      {realNameFor && (
        <div onKeyDown={(event) => {
          if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
            event.preventDefault(); event.stopPropagation(); void assignRealName();
          }
        }}
          style={{ marginTop: 8, padding: 8, background: "#eef4ff", borderRadius: 6 }}>
          <label>Prawdziwe nazwisko osoby „{realNameFor.text}” (z rejestru albo nowa osoba)
            <input autoFocus value={realNameText} maxLength={500} disabled={isRetyping}
              onChange={(event) => setRealNameText(event.target.value)} />
          </label>
          <button type="button" className="button" disabled={isRetyping || !realNameText.trim()}
            onClick={() => void assignRealName()}>Zapisz</button>
          <button type="button" disabled={isRetyping} onClick={() => setRealNameFor(null)}>Anuluj</button>
        </div>
      )}

      {mergeFor && (
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

      {orgMergeFor && (
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
                  <button className={"button"} type="button" onClick={() => {
                    if (o.organization_id != null) {
                      const source = orgMergeFor;
                      setOrgMergeFor(null);
                      void openMergePreview(source, o.organization_id, o.id);
                    } else {
                      void handleOrgMergePick({ targetEntityId: o.id });
                    }
                  }}>
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
              <button className={"button"} type="button" onClick={() => {
                const source = orgMergeFor;
                setOrgMergeFor(null);
                void openMergePreview(source, o.id);
              }}>
                wybierz
              </button>
              {" "}<strong>{o.canonical_name}</strong>
              {o.aliases.length > 0 && <span style={{ color: "#667" }}> ({o.aliases.join(", ")})</span>}
              <span style={{ color: "#999" }}> — {o.document_count} dok.</span>
            </div>
          ))}
        </div>
      )}

      {mergePreview && (mergePreview.data ? (
        <OrganizationMergePreview
          preview={mergePreview.data}
          busy={isMergingOrg}
          onConfirm={() => void confirmMergePreview()}
          onCancel={() => setMergePreview(null)}
        />
      ) : (
        <div style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
          {mergePreview.error ?? "Pobieram porównanie organizacji…"}
          <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setMergePreview(null)}>✕ zamknij</button>
        </div>
      ))}

      {personDocMergeFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Połącz „{personDocMergeFor.item.text}” z inną osobą (zostanie nazwą połączonej osoby):
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setPersonDocMergeFor(null)}>✕ anuluj</button>
          </div>
          {personDocMergeFor.chapter && (
            <label style={{ marginRight: 12 }}>
              <input type="checkbox" checked={personMergeAll} onChange={(event) => setPersonMergeAll(event.target.checked)} />{" "}
              cały dokument (domyślnie tylko ten rozdział)
            </label>
          )}
          <input type="search" value={personMergeQuery} placeholder="Szukaj osoby…" aria-label="Szukaj osoby do połączenia"
            onChange={(event) => setPersonMergeQuery(event.target.value)} style={{ padding: "2px 6px", marginBottom: 4 }} />
          {(() => {
            // People sharing a word with the source ("Andy Stone" for "Stone") come first.
            const words = personDocMergeFor.item.text.toLowerCase().split(/\s+/);
            const shares = (person: EntityItem) => person.text.toLowerCase().split(/\s+/).some((word) => words.includes(word));
            const needle = personMergeQuery.trim().toLowerCase();
            const pool = personDocMergeFor.chapter && !personMergeAll ? personDocMergeFor.chapter : persons;
            return pool.filter((person) => person.id !== personDocMergeFor.item.id && person.id != null
              && (!needle || person.text.toLowerCase().includes(needle)))
              .sort((a, b) => Number(shares(b)) - Number(shares(a)) || a.text.localeCompare(b.text, "pl"));
          })().map((person) => (
            <div key={person.id} style={{ padding: "3px 0" }}>
              <button className={"button"} type="button" disabled={isMergingPlace}
                onClick={() => void mergeDocumentPersons(personDocMergeFor.item, person)}>wybierz</button>
              {" "}<strong>{person.text}</strong>
            </div>
          ))}
        </div>
      )}

      {placeMergeFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Połącz „{placeMergeFor.text}" z innym miejscem w tym dokumencie:
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setPlaceMergeFor(null)}>✕ anuluj</button>
          </div>
          <input type="search" value={placeMergeQuery} placeholder="Szukaj miejsca…" aria-label="Szukaj miejsca do połączenia"
            onChange={(event) => setPlaceMergeQuery(event.target.value)} style={{ padding: "2px 6px", marginBottom: 4 }} />
          {(() => {
            // Names that start alike come first ("Rijad" for "Riad"), then the rest alphabetically.
            const own = placeMergeFor.text.toLowerCase();
            const prefix = (name: string) => {
              const other = name.toLowerCase();
              let n = 0;
              while (n < own.length && n < other.length && own[n] === other[n]) n += 1;
              return n;
            };
            const needle = placeMergeQuery.trim().toLowerCase();
            return places.filter((p) => p.id !== placeMergeFor.id && (!needle || p.text.toLowerCase().includes(needle)))
              .sort((a, b) => prefix(b.text) - prefix(a.text) || a.text.localeCompare(b.text, "pl"));
          })().map((p) => (
            <div key={p.id} style={{ padding: "3px 0" }}>
              <button className={"button"} type="button" onClick={() => handlePlaceMergePick(p)}>wybierz</button>
              {" "}<strong>{p.text}</strong>
            </div>
          ))}
        </div>
      )}

      {sourceDetailsFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0fff4", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Dane źródła: <strong>{sourceDetailsFor.text}</strong>
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setSourceDetailsFor(null)}>✕ anuluj</button>
          </div>
          <label style={{ display: "block" }}>Typ źródła
            <input list="entities-source-types" value={sourceType} maxLength={30} disabled={isSavingSource}
              placeholder="np. gazeta, portal, agencja" onChange={(event) => setSourceType(event.target.value)}
              style={{ padding: "4px 8px", marginLeft: 6, width: 220 }} />
            <datalist id="entities-source-types">
              {["newspaper", "portal", "news agency", "agency", "institution", "company", "organization"].map((type) => (
                <option key={type} value={type} />
              ))}
            </datalist>
          </label>
          <label style={{ display: "block", marginTop: 4 }}>Strona (adres lub domena)
            <input value={sourceDomain} disabled={isSavingSource} placeholder="np. https://www.telegraph.co.uk/"
              onChange={(event) => setSourceDomain(event.target.value)}
              style={{ padding: "4px 8px", marginLeft: 6, width: 280 }} />
          </label>
          <label style={{ display: "block", marginTop: 4 }}>Opis (np. rok założenia, kraj, profil)
            <textarea value={sourceDescription} disabled={isSavingSource} rows={3} maxLength={2000}
              placeholder="np. brytyjski dziennik założony w 1855 w Londynie"
              onChange={(event) => setSourceDescription(event.target.value)}
              style={{ display: "block", padding: "4px 8px", width: "min(520px, 95%)" }} />
          </label>
          <button className={"button"} type="button" style={{ marginTop: 6 }} disabled={isSavingSource}
            onClick={() => void handleSourceDetailsSubmit()}>Zapisz</button>
        </div>
      )}

      {orgDescriptionFor && (
        <div style={{ marginTop: 8, padding: 8, background: "#f0fff4", borderRadius: 6 }}>
          <div style={{ marginBottom: 4 }}>
            Krótki opis dla: <strong>{orgDescriptionFor.text}</strong> (widoczny jako podpowiedź na chipie w czytniku)
            <button type="button" style={{ ...chipActionStyle, marginLeft: 8 }} onClick={() => setOrgDescriptionFor(null)}>✕ anuluj</button>
          </div>
          <textarea
            value={orgDescriptionText}
            onChange={(e) => setOrgDescriptionText(e.target.value)}
            placeholder="np. francuski operator energetyczny, właściciel elektrowni jądrowych"
            rows={2}
            style={{ padding: "4px 8px", width: "min(420px, 95%)" }}
          />
          <div>
            <button className={"button"} type="button" style={{ marginTop: 6 }} onClick={handleOrgDescriptionSubmit}>
              Zapisz
            </button>
            <button className={"button"} type="button" style={{ marginTop: 6, marginLeft: 8 }}
              disabled={orgDescriptionBusy || orgDescriptionFor.id == null} onClick={handleOrgDescriptionSuggest}
              title="Pokaż prompt i wybierz model; opis powstaje z rozdziału, w którym organizacja pada najczęściej">
              {orgDescriptionBusy && !orgPromptOpen ? "Pracuję…" : "🤖 Zaproponuj z tekstu"}
            </button>
          </div>
          {orgPromptOpen && (
            <div style={{ marginTop: 8 }}>
              <label style={{ display: "block" }}>Model
                <select value={orgModel} onChange={(e) => setOrgModel(e.target.value)} style={{ marginLeft: 6 }}>
                  {orgModels.map((model) => <option key={model.id} value={model.id}>{modelOptionText(model)}</option>)}
                </select>
              </label>
              <label style={{ display: "block", marginTop: 6 }}>Prompt wysyłany do modelu (możesz go zmienić)
                <textarea value={orgPrompt} onChange={(e) => setOrgPrompt(e.target.value)} rows={10} maxLength={16000}
                  style={{ display: "block", width: "min(720px, 95%)", boxSizing: "border-box" }} />
              </label>
              <button className={"button"} type="button" style={{ marginTop: 6 }}
                disabled={orgDescriptionBusy || !orgPrompt.trim()} onClick={handleOrgDescriptionGenerate}>
                {orgDescriptionBusy ? "Pracuję…" : "Generuj"}
              </button>
              {orgDescriptionInfo && <span style={{ marginLeft: 8, color: "#475569" }}>{orgDescriptionInfo}</span>}
              {orgModels.find((model) => model.id === orgModel)?.external && (
                <p role="note" style={{ margin: "6px 0 0", color: "#92400e" }}>
                  ⚠ Ten model wysyła tekst rozdziału do zewnętrznego pośrednika (OpenRouter).
                  {orgModels.find((model) => model.id === orgModel)?.verified === false && " Jakość odpowiedzi po polsku nie jest jeszcze sprawdzona (cena i limity pochodzą z katalogu OpenRouter)."}
                </p>
              )}
              <div style={{ marginTop: 10 }}>
                <button type="button" onClick={() => setArenaOpen((open) => !open)}>
                  {arenaOpen ? "▾" : "▸"} ⚔ Arena — porównaj modele
                </button>
                {arenaOpen && (
                  <div style={{ marginTop: 6 }}>
                    <div>Wybierz od 2 do 4 modeli (ten sam prompt trafi do wszystkich):</div>
                    {orgModels.map((model) => (
                      <label key={model.id} style={{ display: "block" }}>
                        <input type="checkbox" checked={arenaModels.includes(model.id)} onChange={() => toggleArenaModel(model.id)} />
                        {" "}{modelOptionText(model)}{model.external ? " ⚠ zewnętrzny" : ""}
                      </label>
                    ))}
                    <button className={"button"} type="button" style={{ marginTop: 6 }}
                      disabled={orgDescriptionBusy || arenaModels.length < 2 || !orgPrompt.trim()} onClick={handleArenaRun}>
                      {orgDescriptionBusy ? "Pracuję…" : "Porównaj"}
                    </button>
                    {arenaResults.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                        {arenaResults.map((result) => (
                          <div key={result.model} style={{ flex: "1 1 220px", maxWidth: 340, padding: 8, background: "#fff", border: "1px solid #cbd5e1", borderRadius: 6 }}>
                            <strong>{result.label}</strong>
                            <div style={{ fontSize: "0.8em", color: "#64748b" }}>
                              {result.latency_ms} ms
                              {result.tokens != null && ` · ${result.tokens} tok.`}
                              {result.cost != null ? ` · ${result.cost} ${result.currency ?? ""}` : " · koszt nieznany"}
                            </div>
                            <p style={{ margin: "6px 0" }}>
                              {result.result_status === "ok" && result.description}
                              {result.result_status === "insufficient_context" && "Model uznał, że rozdział nie wystarcza do opisu."}
                              {result.result_status === "error" && `Model nie odpowiedział: ${result.error_code ?? "błąd"}.`}
                            </p>
                            {result.result_status === "ok" && result.description && (
                              <button type="button" onClick={() => { setOrgDescriptionText(result.description ?? ""); setOrgDescriptionInfo(`Propozycja: ${result.label}`); }}>
                                Użyj tego opisu
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
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
      </div>

      {isEmpty && !message && (
        <div style={{ marginTop: "6px", color: "#667" }}>
          Brak zapisanych encji — użyj przycisku, aby je wykryć.
        </div>
      )}
      {message && (
        <div style={{ marginTop: "6px", color: message.startsWith("Pełna weryfikacja") ? "#2e7d43" : "#a33" }}>
          {message}
        </div>
      )}
    </div>
  );
};

export default EntitiesPanel;
