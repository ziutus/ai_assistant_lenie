import React from "react";
import axios from "axios";
import { Link, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// One product or system (/products/:name): description shared by every document, the spellings found in
// texts and the documents that mention it (productName rows of document_entities with the same name).

interface ProductDocument {
  id: number; title: string | null; mentions: number; entity_id: number;
  document_type: string | null; created_at: string | null;
}
interface ProductInfo { name: string; description: string | null; variants: string[]; mentions: number; documents: ProductDocument[] }

const ProductDetail = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const { name = "" } = useParams();
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);
  const [product, setProduct] = React.useState<ProductInfo | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [isEditing, setIsEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");
  const [isSaving, setIsSaving] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");
    axios.get(`${apiUrl}/entity_product`, { headers, params: { name } })
      .then((response) => { if (!cancelled) setProduct(response.data); })
      .catch((reason: any) => {
        if (!cancelled) {
          setProduct(null);
          setError(`Nie udało się pobrać produktu: ${reason.response?.data?.message || reason.message}`);
        }
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, headers, name]);

  const saveDescription = async () => {
    if (!product) return;
    setIsSaving(true);
    setError("");
    try {
      const response = await axios.put(`${apiUrl}/entity_product/description`,
        { name: product.name, description: draft }, { headers });
      setProduct({ ...product, description: response.data.description ?? null });
      setIsEditing(false);
    } catch (reason: any) {
      setError(`Nie udało się zapisać opisu: ${reason.response?.data?.message || reason.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div>
      <p style={{ marginBottom: 6 }}><Link to="/products">← Produkty i systemy</Link></p>
      {isLoading && <p style={{ color: "#64748b" }}>Wczytuję…</p>}
      {error && <p role="alert" style={{ color: "#a33" }}>{error}</p>}
      {product && (
        <>
          <h2 style={{ marginBottom: 4 }}>🛰️ {product.name}</h2>
          <p style={{ color: "#64748b", marginTop: 0 }}>
            {product.documents.length} dok. · {product.mentions} wzmianek
          </p>

          <section aria-label="Opis produktu" style={{ marginBottom: 16 }}>
            <h3 style={{ marginBottom: 4 }}>Opis</h3>
            {isEditing ? (
              <div>
                <textarea aria-label="Opis produktu" rows={5} maxLength={2000} value={draft}
                  onChange={(event) => setDraft(event.target.value)} style={{ width: "100%", maxWidth: 720 }} />
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  <button type="button" className="button" disabled={isSaving} onClick={saveDescription}>Zapisz</button>
                  <button type="button" className="button" disabled={isSaving} onClick={() => setIsEditing(false)}>Anuluj</button>
                </div>
              </div>
            ) : (
              <div>
                <p style={{ margin: "4px 0", whiteSpace: "pre-wrap", color: product.description ? undefined : "#94a3b8" }}>
                  {product.description || "Brak opisu."}
                </p>
                <button type="button" className="button"
                  onClick={() => { setDraft(product.description ?? ""); setIsEditing(true); }}>
                  {product.description ? "Edytuj opis" : "Dodaj opis"}
                </button>
              </div>
            )}
          </section>

          {product.variants.length > 0 && (
            <section aria-label="Pisownie" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 4 }}>Pisownie w tekstach</h3>
              <p style={{ margin: 0 }}>{product.variants.join(", ")}</p>
            </section>
          )}

          <section aria-label="Dokumenty">
            <h3 style={{ marginBottom: 4 }}>Dokumenty</h3>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {product.documents.map((document) => (
                <li key={document.entity_id} style={{ padding: "6px 10px", marginBottom: 6, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
                  <Link to={`/webpage/${document.id}`}>{document.title || `Dokument ${document.id}`}</Link>{" "}
                  <span style={{ color: "#64748b", fontSize: "0.85em" }}>
                    ×{document.mentions}{document.document_type ? ` · ${document.document_type}` : ""}
                    {document.created_at ? ` · ${document.created_at.slice(0, 10)}` : ""}
                  </span>{" "}
                  <Link to={`/ner/${document.id}`} style={{ fontSize: "0.85em" }}>NER</Link>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
};

export default ProductDetail;
