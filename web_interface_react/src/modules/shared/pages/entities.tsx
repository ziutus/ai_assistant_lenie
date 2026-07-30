import React from "react";
import axios from "axios";
import { NavLink, useParams } from "react-router-dom";
import EntitiesPanel from "../components/EntitiesPanel/entitiesPanel";
import { AuthorizationContext } from "../context/authorizationContext";

type DocumentSummary = { title?: string; document_type?: string; entities_checked_at?: string | null };

/** Dedicated review step for NER: it is intentionally separate from editing. */
const Entities = () => {
  const { id } = useParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [document, setDocument] = React.useState<DocumentSummary | null>(null);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    axios.get(`${apiUrl}/website_get`, { params: { id }, headers: { "x-api-key": `${apiKey}` } })
      .then((response) => { if (!cancelled) setDocument(response.data); })
      .catch((requestError) => {
        if (!cancelled) setError(`Nie udało się pobrać dokumentu: ${requestError.response?.data?.message || requestError.message}`);
      });
    return () => { cancelled = true; };
  }, [apiKey, apiUrl, id]);

  if (!id) return <p>Brak identyfikatora dokumentu.</p>;
  const editorPath = document?.document_type ? `/${document.document_type}/${id}` : null;
  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Encje dokumentu</h2><span style={{ color: "#64748b" }}>#{id}</span>
        {editorPath && <NavLink to={editorPath} style={{ fontSize: "0.9em", color: "#0369a1" }}>← Edytuj dokument</NavLink>}
        <NavLink to={`/read/${id}`} style={{ fontSize: "0.9em", color: "#0369a1" }}>Czytaj dokument</NavLink>
        <NavLink to={`/chunks/${id}`} style={{ fontSize: "0.9em", color: "#0369a1" }}>Przegląd chunków</NavLink>
      </div>
      {document?.title && <h3 style={{ margin: "0 0 8px" }}>{document.title}</h3>}
      <p style={{ margin: "0 0 14px", color: "#475569" }}>Etap 2: wykrywanie i porządkowanie osób, miejsc oraz organizacji.{document?.entities_checked_at && ` Ostatnia analiza: ${new Date(document.entities_checked_at).toLocaleString("pl-PL")}.`}</p>
      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      <EntitiesPanel docId={id} />
      <section style={{ marginTop: 20, padding: 16, borderTop: "1px solid #cbd5e1", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <NavLink className="button" to={`/chunks/${id}`} style={{ fontSize: "1em", fontWeight: 700 }}>
          Przejdź do przeglądu chunków →
        </NavLink>
        {editorPath && (
          <NavLink to={editorPath} style={{ color: "#0369a1" }}>
            Wróć do edycji dokumentu
          </NavLink>
        )}
      </section>
    </div>
  );
};

export default Entities;
