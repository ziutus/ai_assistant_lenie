import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";

// Read-only gallery of a document's images (backend: GET /document/:id/images,
// table document_images — url-sourced from article_cleaner.clean_article_text()
// for webpage/link documents, or storage_key-sourced book-PDF illustrations).
// Collapsed by default; thumbnails only load once opened.

export interface DocumentImageItem {
  position: number | null;
  url: string | null;
  caption_text: string | null;
  alt_text: string | null;
  page_number: number | null;
  chapter_position: number | null;
  is_local: boolean;
}

interface Props {
  docId: number | string;
}

const DocumentImagesPanel: React.FC<Props> = ({ docId }) => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const [images, setImages] = React.useState<DocumentImageItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    if (!docId) return;
    setLoading(true);
    setError("");
    axios
      .get(`${apiUrl}/document/${docId}/images`, { headers: { "x-api-key": `${apiKey}` } })
      .then((response) => setImages(response.data.images ?? []))
      .catch((err: any) => {
        setError(err.response?.data?.message || err.message || "Nie udało się pobrać ilustracji.");
      })
      .finally(() => {
        setLoading(false);
        setLoaded(true);
      });
  }, [apiUrl, apiKey, docId]);

  // Nothing to show and no error — don't clutter the editor with an empty panel.
  if (loaded && images.length === 0 && !error) return null;

  return (
    <section style={{
      marginTop: 14, padding: 14, border: "1px solid #e2e8f0",
      borderRadius: 8, background: "#f8fafc",
    }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
        onClick={() => setOpen((value) => !value)}
      >
        <strong style={{ color: "#334155" }}>
          🖼️ Ilustracje{images.length ? ` (${images.length})` : ""}
        </strong>
        <span style={{ marginLeft: "auto", color: "#64748b" }}>
          {loading ? "…" : open ? "▲" : "▼"}
        </span>
      </div>

      {open && (
        <div style={{ marginTop: 10 }}>
          {error && <div style={{ color: "#b91c1c", fontSize: "0.85em", marginBottom: 6 }}>{error}</div>}

          {images.length === 0 && !loading && !error && (
            <div style={{ color: "#64748b", fontSize: "0.88em" }}>Brak ilustracji.</div>
          )}

          {images.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              {images.map((img, idx) => (
                <figure key={`${img.position ?? idx}`} style={{ width: 160, margin: 0 }}>
                  {img.url ? (
                    <div style={{ position: "relative" }}>
                      <a href={img.url} target="_blank" rel="noreferrer">
                        <img
                          src={img.url}
                          alt={img.alt_text ?? ""}
                          loading="lazy"
                          style={{
                            width: "100%", height: 110, objectFit: "cover",
                            borderRadius: 4, border: "1px solid #cbd5e1", background: "#fff",
                          }}
                        />
                      </a>
                      <span
                        title={img.is_local ? "Kopia w storage (MinIO)" : "Zewnętrzny URL (poza Lenie)"}
                        style={{
                          position: "absolute", top: 4, left: 4, fontSize: "0.72em",
                          padding: "1px 5px", borderRadius: 4, color: "#fff",
                          background: img.is_local ? "rgba(22,101,52,0.85)" : "rgba(30,41,59,0.75)",
                        }}
                      >
                        {img.is_local ? "📦 storage" : "🔗 zewnętrzny"}
                      </span>
                    </div>
                  ) : (
                    <div style={{
                      width: "100%", height: 110, borderRadius: 4, border: "1px dashed #cbd5e1",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      color: "#94a3b8", fontSize: "0.8em", textAlign: "center", padding: 6,
                    }}>
                      brak podglądu
                    </div>
                  )}
                  {(img.caption_text || img.alt_text) && (
                    <figcaption style={{ fontSize: "0.78em", color: "#475569", marginTop: 4 }}>
                      {img.caption_text || img.alt_text}
                    </figcaption>
                  )}
                </figure>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default DocumentImagesPanel;
