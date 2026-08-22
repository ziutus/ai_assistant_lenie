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
    setDocuments([]);
    setOccurrences({});
    setIsEditing(false);
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
        <ul style={{ listStyle: "none", padding: 0 }}>
          {organizations.map((o) => (
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
      )}
    </div>
  );
};

export default Organizations;
