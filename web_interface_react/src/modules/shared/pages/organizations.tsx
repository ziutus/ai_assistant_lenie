import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// Global organization registry browser (library/organization_registry.py):
// fuzzy search over organizations/aliases (GET /organizations?q=) and the
// organization -> documents view (GET /organizations/<id>/documents).

export interface OrganizationItem {
  id: number;
  uuid?: string;
  canonical_name: string;
  organization_type: string | null;
  description: string | null;
  aliases: string[];
  document_count?: number;
}

interface OrganizationAlias {
  id: number;
  alias: string;
  alias_kind: string;
  created_by: string | null;
}

// A text this organization shares with another, unrelated organization
// (organization_ambiguous_aliases — e.g. "Africa Corps" meaning either the
// Russian 2023+ formation or a rendering of WWII's "Afrika Korps").
// entity_service resolves these per-mention via an LLM context check
// instead of always landing on this organization.
interface AmbiguousWith {
  alias: string;
  context_hint: string | null;
  other_organizations: {
    id: number;
    canonical_name: string;
    organization_type: string | null;
    description: string | null;
    context_hint: string | null;
  }[];
}

interface OrganizationDocument {
  link_id: number;
  id: number;
  title: string;
  document_type: string;
  raw_mention: string | null;
  mention_count: number;
  confidence: string;
  review_status: string;
}

// Per-chapter occurrence counts (GET /document/:id/entity_occurrences?text=)
interface ChapterOccurrence {
  position: number;
  title: string;
  count: number;
}

const EDITOR_TYPES = ["webpage", "link", "youtube", "movie", "email"];

const CONFIDENCE_LABELS: Record<string, string> = {
  alias_matched: "✓ alias",
  canonical_matched: "✓ nazwa",
  manual_confirmed: "✓ potwierdzone",
  context_llm_matched: "✓ LLM",
  needs_review: "? do weryfikacji",
};

export const OrganizationHeader = ({
  organization,
}: {
  organization: Pick<OrganizationItem, "canonical_name" | "description" | "organization_type"> & { aliases?: string[] };
}) => (
  <div style={{ display: "inline-block", verticalAlign: "top" }}>
    <strong>{organization.canonical_name}</strong>
    {organization.organization_type && (
      <span style={{ marginLeft: 8, fontSize: "0.85em", color: "#0369a1" }}>[{organization.organization_type}]</span>
    )}
    {organization.description && <span style={{ marginLeft: 8, color: "#667" }}>{organization.description}</span>}
    {!!organization.aliases?.length && (
      <div style={{ fontSize: "0.85em", color: "#667" }}>Aliasy: {organization.aliases.join(", ")}</div>
    )}
  </div>
);

const Organizations = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  // ?q= pre-fills the search — unresolved orgName chips in the reader link here
  const initialQuery = searchParams.get("q") ?? "";
  const [query, setQuery] = React.useState(initialQuery);
  const [organizations, setOrganizations] = React.useState<OrganizationItem[]>([]);
  const [organization, setOrganization] = React.useState<
    { id: number; canonical_name: string; description: string | null; organization_type: string | null } | null
  >(null);
  const [aliases, setAliases] = React.useState<OrganizationAlias[]>([]);
  const [ambiguousWith, setAmbiguousWith] = React.useState<AmbiguousWith[]>([]);
  const [documents, setDocuments] = React.useState<OrganizationDocument[]>([]);
  // per-document chapter drill-down ("wystąpienia w tej książce")
  const [occurrences, setOccurrences] = React.useState<Record<number, ChapterOccurrence[] | "loading">>({});
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);

  const [editDescription, setEditDescription] = React.useState("");
  const [editType, setEditType] = React.useState("");
  const [isEditing, setIsEditing] = React.useState(false);
  const [newAlias, setNewAlias] = React.useState("");
  const [busyLinkId, setBusyLinkId] = React.useState<number | null>(null);
  const [sortBy, setSortBy] = React.useState<"count" | "name">("count");
  const [showMergePicker, setShowMergePicker] = React.useState(false);
  const [mergeQuery, setMergeQuery] = React.useState("");
  const [mergeResults, setMergeResults] = React.useState<OrganizationItem[]>([]);
  const [isMerging, setIsMerging] = React.useState(false);

  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "x-api-key": `${apiKey}`,
  };
  const jsonHeaders = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  const search = async (q: string) => {
    setIsLoading(true);
    setMessage("");
    setIsError(false);
    try {
      const response = await axios.get(`${apiUrl}/organizations`, { params: q ? { q } : {}, headers });
      setOrganizations(response.data.entries ?? []);
      if (!(response.data.entries ?? []).length) {
        setMessage(q ? "Brak organizacji pasujących do zapytania." : "Rejestr organizacji jest pusty.");
      }
    } catch (error: any) {
      console.error("Error searching organizations", error);
      setIsError(true);
      setMessage(`Nie udało się wyszukać organizacji: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    search(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sortedOrganizations = React.useMemo(() => {
    const list = [...organizations];
    if (sortBy === "name") {
      list.sort((a, b) => a.canonical_name.localeCompare(b.canonical_name, "pl"));
    } else {
      list.sort((a, b) =>
        (b.document_count ?? 0) - (a.document_count ?? 0)
        || a.canonical_name.localeCompare(b.canonical_name, "pl"));
    }
    return list;
  }, [organizations, sortBy]);

  const loadDetail = async () => {
    if (!id) return;
    setIsLoading(true);
    setMessage("");
    setIsError(false);
    try {
      const [orgResponse, docsResponse] = await Promise.all([
        axios.get(`${apiUrl}/organizations/${id}`, { headers }),
        axios.get(`${apiUrl}/organizations/${id}/documents`, { headers }),
      ]);
      setOrganization(orgResponse.data);
      setAliases(orgResponse.data.aliases ?? []);
      setAmbiguousWith(orgResponse.data.ambiguous_with ?? []);
      setEditDescription(orgResponse.data.description ?? "");
      setEditType(orgResponse.data.organization_type ?? "");
      setDocuments(docsResponse.data.documents ?? []);
    } catch (error: any) {
      console.error("Error fetching organization documents", error);
      setIsError(true);
      setMessage(`Nie udało się pobrać danych organizacji: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    setOrganization(null);
    setAliases([]);
    setAmbiguousWith([]);
    setDocuments([]);
    setOccurrences({});
    setIsEditing(false);
    setShowMergePicker(false);
    setMergeQuery("");
    setMergeResults([]);
    if (!id) return;
    loadDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const toggleOccurrences = async (doc: OrganizationDocument) => {
    if (!doc.raw_mention) return;
    if (occurrences[doc.id]) {
      setOccurrences((prev) => {
        const next = { ...prev };
        delete next[doc.id];
        return next;
      });
      return;
    }
    setOccurrences((prev) => ({ ...prev, [doc.id]: "loading" }));
    try {
      const response = await axios.get(`${apiUrl}/document/${doc.id}/entity_occurrences`, {
        params: { text: doc.raw_mention }, headers,
      });
      setOccurrences((prev) => ({ ...prev, [doc.id]: response.data.occurrences ?? [] }));
    } catch (error: any) {
      console.error("Error fetching occurrences", error);
      setOccurrences((prev) => {
        const next = { ...prev };
        delete next[doc.id];
        return next;
      });
      setMessage(`Nie udało się pobrać wystąpień: ${error.response?.data?.message || error.message}`);
      setIsError(true);
    }
  };

  const saveEdits = async () => {
    if (!organization) return;
    setIsLoading(true);
    setMessage("");
    setIsError(false);
    try {
      const response = await axios.patch(`${apiUrl}/organizations/${organization.id}`, {
        description: editDescription, organization_type: editType,
      }, { headers: jsonHeaders });
      setOrganization((prev) => prev ? { ...prev, description: response.data.description, organization_type: response.data.organization_type } : prev);
      setIsEditing(false);
      setMessage("Zapisano zmiany.");
    } catch (error: any) {
      console.error("Error updating organization", error);
      setIsError(true);
      setMessage(`Nie udało się zapisać zmian: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  const addAlias = async () => {
    if (!organization || !newAlias.trim()) return;
    setMessage("");
    setIsError(false);
    try {
      const response = await axios.post(`${apiUrl}/organizations/${organization.id}/aliases`, {
        alias: newAlias.trim(),
      }, { headers: jsonHeaders });
      setAliases((prev) => [...prev, { id: response.data.alias_id, alias: response.data.alias, alias_kind: "manual", created_by: "manual" }]);
      setNewAlias("");
    } catch (error: any) {
      console.error("Error adding alias", error);
      setIsError(true);
      setMessage(`Nie udało się dodać aliasu: ${error.response?.data?.message || error.message}`);
    }
  };

  const removeAlias = async (aliasId: number) => {
    if (!organization) return;
    setMessage("");
    setIsError(false);
    try {
      await axios.delete(`${apiUrl}/organizations/${organization.id}/aliases/${aliasId}`, { headers });
      setAliases((prev) => prev.filter((a) => a.id !== aliasId));
    } catch (error: any) {
      console.error("Error removing alias", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć aliasu: ${error.response?.data?.message || error.message}`);
    }
  };

  const searchMergeTargets = async () => {
    if (!organization) return;
    setIsMerging(true);
    setMessage("");
    setIsError(false);
    try {
      const response = await axios.get(`${apiUrl}/organizations`, {
        params: mergeQuery.trim() ? { q: mergeQuery.trim() } : {}, headers,
      });
      const found = (response.data.entries ?? []).filter((o: OrganizationItem) => o.id !== organization.id);
      setMergeResults(found);
      if (!found.length) {
        setMessage("Brak innych organizacji pasujących do zapytania.");
      }
    } catch (error: any) {
      console.error("Error searching organizations for merge", error);
      setIsError(true);
      setMessage(`Nie udało się wyszukać organizacji: ${error.response?.data?.message || error.message}`);
    }
    setIsMerging(false);
  };

  // Merges `organization` (the row currently open) INTO `targetId`, globally
  // — duplicate cleanup for the exact-match-only registry (no fuzzy
  // auto-merge, see docs/organization-ner-alias-plan.md). The source row is
  // deleted once orphaned, so we navigate to the surviving target.
  const mergeInto = async (targetId: number) => {
    if (!organization) return;
    setIsMerging(true);
    setMessage("");
    setIsError(false);
    try {
      await axios.post(`${apiUrl}/organizations/${organization.id}/merge`, {
        target_organization_id: targetId,
      }, { headers: jsonHeaders });
      setShowMergePicker(false);
      navigate(`/organizations/${targetId}`);
    } catch (error: any) {
      console.error("Error merging organizations", error);
      setIsError(true);
      setMessage(`Nie udało się scalić organizacji: ${error.response?.data?.message || error.message}`);
    }
    setIsMerging(false);
  };

  const approveLink = async (doc: OrganizationDocument) => {
    setBusyLinkId(doc.link_id);
    setMessage("");
    setIsError(false);
    try {
      await axios.post(`${apiUrl}/document/${doc.id}/organizations/${doc.link_id}/approve`, {}, { headers: jsonHeaders });
      setDocuments((prev) => prev.map((d) => d.link_id === doc.link_id ? { ...d, review_status: "approved" } : d));
    } catch (error: any) {
      console.error("Error approving organization link", error);
      setIsError(true);
      setMessage(`Nie udało się zatwierdzić: ${error.response?.data?.message || error.message}`);
    }
    setBusyLinkId(null);
  };

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Organizacje</h2>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          search(query.trim());
        }}
        style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}
      >
        <input
          type="text"
          value={query}
          placeholder="Szukaj organizacji (nazwa lub alias)..."
          onChange={(e) => setQuery(e.target.value)}
          style={{ minWidth: 320, padding: "6px 10px" }}
          disabled={isLoading}
        />
        <button type="submit" className={"button"} disabled={isLoading}>
          Szukaj
        </button>
      </form>

      {isLoading && <div className={"loader"}></div>}
      {message && (
        <p className={isError ? "errorText" : undefined} style={isError ? undefined : { color: "#2e7d43" }}>
          {message}
        </p>
      )}

      {id && organization ? (
        <div style={{ marginBottom: 20, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
          {!isEditing ? (
            <div>
              <OrganizationHeader organization={{ ...organization, aliases: aliases.map((a) => a.alias) }} />
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                style={{ marginLeft: 10, fontSize: "0.85em", color: "#0369a1", border: "none", background: "none", cursor: "pointer" }}
              >
                ✏️ Edytuj
              </button>
              <button
                type="button"
                onClick={() => setShowMergePicker((prev) => !prev)}
                style={{ marginLeft: 10, fontSize: "0.85em", color: "#0369a1", border: "none", background: "none", cursor: "pointer" }}
                title="Ta organizacja jest duplikatem innej — scal obie w jedną"
              >
                🔀 Scal z inną organizacją...
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 480 }}>
              <strong>{organization.canonical_name}</strong>
              <input
                type="text"
                value={editType}
                placeholder="Typ organizacji (np. firma, agencja rządowa...)"
                onChange={(e) => setEditType(e.target.value)}
                style={{ padding: "6px 10px" }}
              />
              <textarea
                value={editDescription}
                placeholder="Krótki opis (pokazywany jako tooltip na chipie w czytniku)"
                onChange={(e) => setEditDescription(e.target.value)}
                rows={2}
                style={{ padding: "6px 10px" }}
              />
              <div style={{ display: "flex", gap: 8 }}>
                <button className={"button"} type="button" onClick={saveEdits}>Zapisz</button>
                <button className={"button"} type="button" onClick={() => setIsEditing(false)}>Anuluj</button>
              </div>
            </div>
          )}

          {ambiguousWith.length > 0 && (
            <div style={{
              marginTop: 12, padding: 8, background: "#fff7ed", border: "1px solid #fdba74",
              borderRadius: 6, fontSize: "0.9em", color: "#9a3412",
            }}>
              {ambiguousWith.map((entry) => (
                <div key={entry.alias} style={{ marginBottom: 8 }}>
                  <div>
                    ⚠️ Nazwa „{entry.alias}” jest niejednoznaczna — rozstrzygana automatycznie dla każdej
                    wzmianki na podstawie kontekstu dokumentu (LLM); warto zweryfikować dopasowania w liście
                    dokumentów poniżej.
                  </div>
                  {entry.context_hint && (
                    <div style={{ marginTop: 4 }}>
                      <strong>Tutaj gdy:</strong> {entry.context_hint}
                    </div>
                  )}
                  {entry.other_organizations.map((other) => (
                    <div key={other.id} style={{ marginTop: 4 }}>
                      <strong>Ale nie mylić z: </strong>
                      <NavLink to={`/organizations/${other.id}`} style={{ color: "#9a3412", textDecoration: "underline" }}>
                        {other.canonical_name}
                      </NavLink>
                      {other.organization_type && <> [{other.organization_type}]</>}
                      {other.description && <> — {other.description}</>}
                      {other.context_hint && <div>Tam gdy: {other.context_hint}</div>}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 12 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="text"
                value={newAlias}
                placeholder="Dodaj alias..."
                onChange={(e) => setNewAlias(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addAlias();
                  }
                }}
                style={{ padding: "4px 8px", minWidth: 200 }}
              />
              <button className={"button"} type="button" onClick={addAlias}>Dodaj alias</button>
            </div>
            {aliases.length > 0 && (
              <ul style={{ listStyle: "none", padding: 0, marginTop: 6 }}>
                {aliases.map((a) => (
                  <li key={a.id} style={{ fontSize: "0.85em", color: "#667", display: "flex", alignItems: "center", gap: 6 }}>
                    {a.alias} <span style={{ color: "#aaa" }}>({a.alias_kind})</span>
                    <button
                      type="button"
                      onClick={() => removeAlias(a.id)}
                      style={{ border: "none", background: "none", color: "#a33", cursor: "pointer" }}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {showMergePicker && (
            <div style={{ marginTop: 12, padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
              <div style={{ marginBottom: 6, color: "#667", fontSize: "0.9em" }}>
                Scala tę organizację ({organization.canonical_name}) w wybraną — aliasy i dokumenty
                przechodzą na nią, ta zostaje usunięta z rejestru (o ile nie zostanie po niej nic innego).
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="text"
                  value={mergeQuery}
                  placeholder="Szukaj docelowej organizacji..."
                  onChange={(e) => setMergeQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      searchMergeTargets();
                    }
                  }}
                  style={{ minWidth: 260, padding: "4px 8px" }}
                  disabled={isMerging}
                />
                <button className={"button"} type="button" disabled={isMerging} onClick={searchMergeTargets}>
                  Szukaj
                </button>
                <button className={"button"} type="button" onClick={() => setShowMergePicker(false)}>
                  Anuluj
                </button>
              </div>
              {mergeResults.length > 0 && (
                <ul style={{ listStyle: "none", padding: 0, margin: "6px 0 0" }}>
                  {mergeResults.map((o) => (
                    <li key={o.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0" }}>
                      <button className={"button"} type="button" disabled={isMerging} onClick={() => mergeInto(o.id)}>
                        Scal z tą organizacją
                      </button>
                      <OrganizationHeader organization={o} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <h3 style={{ margin: "18px 0 6px" }}>Dokumenty ({documents.length})</h3>
          {!documents.length && <div style={{ color: "#667" }}>Brak dokumentów wspominających tę organizację.</div>}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {documents.map((doc) => (
              <li key={doc.link_id} style={{ padding: "6px 0", borderBottom: "1px solid #eee", opacity: busyLinkId === doc.link_id ? 0.5 : 1 }}>
                <span style={{ color: "#667", fontSize: "0.85em", marginRight: 8 }}>[{doc.document_type}]</span>
                <NavLink to={`/read/${doc.id}${doc.raw_mention ? `?highlight=${encodeURIComponent(doc.raw_mention)}` : ""}`}>
                  {doc.title || `Dokument ${doc.id}`}
                </NavLink>
                {doc.mention_count > 0 && <strong style={{ marginLeft: 8, color: "#334155" }}>×{doc.mention_count}</strong>}
                {EDITOR_TYPES.includes(doc.document_type) && (
                  <NavLink to={`/${doc.document_type}/${doc.id}`} style={{ marginLeft: 10, fontSize: "0.85em", color: "#0369a1" }}>
                    ✏️ Edytuj
                  </NavLink>
                )}
                {doc.raw_mention && (
                  <button
                    type="button"
                    onClick={() => toggleOccurrences(doc)}
                    style={{ marginLeft: 10, fontSize: "0.85em", color: "#0369a1", border: "none", background: "none", cursor: "pointer", padding: 0 }}
                  >
                    {occurrences[doc.id] ? "▾ rozdziały" : "▸ rozdziały"}
                  </button>
                )}
                <span style={{ marginLeft: 10, fontSize: "0.85em", color: "#667" }}>
                  {doc.raw_mention && <>wzmianka: „{doc.raw_mention}” · </>}
                  {CONFIDENCE_LABELS[doc.confidence] ?? doc.confidence}
                </span>
                {doc.review_status === "approved" ? (
                  <span style={{ marginLeft: 10, fontSize: "0.85em", color: "#2e7d43" }}>✓ zatwierdzone</span>
                ) : (
                  <button
                    type="button"
                    disabled={busyLinkId === doc.link_id}
                    onClick={() => approveLink(doc)}
                    style={{ marginLeft: 10, fontSize: "0.85em", color: "#2e7d43", border: "none", background: "none", cursor: "pointer", padding: 0 }}
                    title="Zatwierdź — chroń przed odświeżeniem NER"
                  >
                    ✓ zatwierdź
                  </button>
                )}
                {occurrences[doc.id] === "loading" && (
                  <div style={{ fontSize: "0.85em", color: "#94a3b8", margin: "4px 0 0 20px" }}>Ładowanie…</div>
                )}
                {Array.isArray(occurrences[doc.id]) && (
                  <div style={{ fontSize: "0.85em", margin: "4px 0 0 20px" }}>
                    {(occurrences[doc.id] as ChapterOccurrence[]).length === 0 && (
                      <span style={{ color: "#94a3b8" }}>Brak rozdziałów (dokument bez struktury) lub wystąpień.</span>
                    )}
                    {(occurrences[doc.id] as ChapterOccurrence[]).map((o) => (
                      <div key={o.position} style={{ padding: "1px 0" }}>
                        <NavLink
                          to={`/read/${doc.id}?chapter=${o.position}&highlight=${encodeURIComponent(doc.raw_mention ?? "")}`}
                          style={{ color: "#0369a1" }}
                        >
                          {o.position}. {o.title}
                        </NavLink>
                        <span style={{ color: "#667" }}> ×{o.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <button className={"button"} type="button" style={{ marginTop: 14 }} onClick={() => navigate("/organizations")}>
            ← Wróć do listy
          </button>
        </div>
      ) : (
        <>
          {organizations.length > 1 && (
            <div style={{ marginBottom: 10, display: "flex", gap: 10, alignItems: "center", fontSize: "0.9em" }}>
              <span style={{ color: "#667" }}>Sortuj:</span>
              <button
                type="button"
                onClick={() => setSortBy("count")}
                style={{
                  border: "none", background: "none", cursor: "pointer", padding: 0,
                  color: sortBy === "count" ? "#0369a1" : "#667",
                  fontWeight: sortBy === "count" ? 700 : 400,
                }}
              >
                liczba dokumentów
              </button>
              <button
                type="button"
                onClick={() => setSortBy("name")}
                style={{
                  border: "none", background: "none", cursor: "pointer", padding: 0,
                  color: sortBy === "name" ? "#0369a1" : "#667",
                  fontWeight: sortBy === "name" ? 700 : 400,
                }}
              >
                nazwa (A-Z)
              </button>
            </div>
          )}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {sortedOrganizations.map((o) => (
              <li
                key={o.id}
                style={{ padding: "8px 6px", borderBottom: "1px solid #eee", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
                onClick={() => navigate(`/organizations/${o.id}`)}
              >
                <OrganizationHeader organization={o} />
                {typeof o.document_count === "number" && (
                  <span style={{ color: "#667", fontSize: "0.85em", whiteSpace: "nowrap" }}>{o.document_count} dok.</span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
};

export default Organizations;
