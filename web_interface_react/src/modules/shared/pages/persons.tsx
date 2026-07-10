import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// Person registry browser (NER stage 4): fuzzy search over persons/aliases
// (GET /persons?q=) and the person -> documents view (GET /person_documents).

export interface PersonItem {
  id: number;
  uuid: string;
  canonical_name: string;
  wikidata_qid: string | null;
  description: string | null;
  aliases: string[];
}

interface PersonDocument {
  id: number;
  title: string;
  document_type: string;
  raw_mention: string;
  confidence: string;
}

const EDITOR_TYPES = ["webpage", "link", "youtube", "movie", "email"];

const CONFIDENCE_LABELS: Record<string, string> = {
  wikidata_matched: "✓ Wikidata",
  alias_matched: "✓ alias",
  manual_confirmed: "✓ potwierdzone",
  manual_review: "? do weryfikacji",
};

export const PersonHeader = ({ person }: { person: Pick<PersonItem, "canonical_name" | "description" | "wikidata_qid"> & { aliases?: string[] } }) => (
  <div style={{ display: "inline-block", verticalAlign: "top" }}>
    <strong>{person.canonical_name}</strong>
    {person.wikidata_qid && (
      <a
        href={`https://www.wikidata.org/wiki/${person.wikidata_qid}`}
        target="_blank"
        rel="noreferrer"
        style={{ marginLeft: 8, fontSize: "0.85em", color: "#0369a1" }}
      >
        {person.wikidata_qid}
      </a>
    )}
    {person.description && <span style={{ marginLeft: 8, color: "#667" }}>{person.description}</span>}
    {!!person.aliases?.length && (
      <div style={{ fontSize: "0.85em", color: "#667" }}>Aliasy: {person.aliases.join(", ")}</div>
    )}
  </div>
);

const Persons = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const [query, setQuery] = React.useState("");
  const [persons, setPersons] = React.useState<PersonItem[]>([]);
  const [person, setPerson] = React.useState<
    { canonical_name: string; description: string | null; wikidata_qid: string | null } | null
  >(null);
  const [documents, setDocuments] = React.useState<PersonDocument[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");

  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "x-api-key": `${apiKey}`,
  };

  const search = async (q: string) => {
    setIsLoading(true);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/persons`, { params: q ? { q } : {}, headers });
      setPersons(response.data.persons ?? []);
      if (!(response.data.persons ?? []).length) {
        setMessage(q ? "Brak osób pasujących do zapytania." : "Rejestr osób jest pusty.");
      }
    } catch (error: any) {
      console.error("Error searching persons", error);
      setMessage(`Nie udało się wyszukać osób: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    search("");
  }, []);

  React.useEffect(() => {
    setPerson(null);
    setDocuments([]);
    if (!id) {
      return;
    }
    setIsLoading(true);
    axios
      .get(`${apiUrl}/person_documents`, { params: { id }, headers })
      .then((response) => {
        setPerson(response.data.person);
        setDocuments(response.data.documents ?? []);
      })
      .catch((error) => {
        console.error("Error fetching person documents", error);
        setMessage(`Nie udało się pobrać artykułów osoby: ${error.response?.data?.message || error.message}`);
      })
      .finally(() => setIsLoading(false));
  }, [id]);

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Osoby</h2>

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
          placeholder="Szukaj osoby (nazwa lub alias)..."
          onChange={(e) => setQuery(e.target.value)}
          style={{ minWidth: 320, padding: "6px 10px" }}
          disabled={isLoading}
        />
        <button type="submit" className={"button"} disabled={isLoading}>
          Szukaj
        </button>
      </form>

      {isLoading && <div className={"loader"}></div>}
      {message && <p className={"errorText"}>{message}</p>}

      {id && person ? (
        <div style={{ marginBottom: 20, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
          <PersonHeader person={person} />
          <h3 style={{ margin: "12px 0 6px" }}>Artykuły ({documents.length})</h3>
          {!documents.length && <div style={{ color: "#667" }}>Brak artykułów powiązanych z tą osobą.</div>}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {documents.map((doc) => (
              <li key={doc.id} style={{ padding: "6px 0", borderBottom: "1px solid #eee" }}>
                <span style={{ color: "#667", fontSize: "0.85em", marginRight: 8 }}>[{doc.document_type}]</span>
                {EDITOR_TYPES.includes(doc.document_type) ? (
                  <NavLink to={`/${doc.document_type}/${doc.id}`}>{doc.title || `Dokument ${doc.id}`}</NavLink>
                ) : (
                  <span>{doc.title || `Dokument ${doc.id}`}</span>
                )}
                <NavLink to={`/read/${doc.id}`} style={{ marginLeft: 10, fontSize: "0.85em", color: "#0369a1" }}>
                  📖 Czytaj
                </NavLink>
                <span style={{ marginLeft: 10, fontSize: "0.85em", color: "#667" }}>
                  wzmianka: „{doc.raw_mention}” · {CONFIDENCE_LABELS[doc.confidence] ?? doc.confidence}
                </span>
              </li>
            ))}
          </ul>
          <button className={"button"} type="button" onClick={() => navigate("/persons")}>
            ← Wróć do listy
          </button>
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {persons.map((p) => (
            <li
              key={p.id}
              style={{ padding: "8px 6px", borderBottom: "1px solid #eee", cursor: "pointer" }}
              onClick={() => navigate(`/persons/${p.id}`)}
            >
              <PersonHeader person={p} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default Persons;
