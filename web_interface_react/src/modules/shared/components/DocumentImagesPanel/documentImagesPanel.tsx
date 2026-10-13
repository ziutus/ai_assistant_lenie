import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";

// Gallery of a document's images (backend: GET /document/:id/images,
// table document_images — url-sourced from article_cleaner.clean_article_text()
// for webpage/link documents, or storage_key-sourced book-PDF illustrations).
// Collapsed by default; thumbnails only load once opened.
//
// Images with an external URL can be copied into our own storage (MinIO) one by
// one or all at once (POST /document/:id/images/download). Removing the
// "[imgN]" marker from the article text and saving drops the image from this
// list (backend: DocumentService.save_document) — `refreshKey` reloads it.

export interface DocumentImageItem {
  id?: number;
  position: number | null;
  url: string | null;
  source_url?: string | null;
  caption_text: string | null;
  alt_text: string | null;
  page_number: number | null;
  chapter_position: number | null;
  is_local: boolean;
}

interface Props {
  docId: number | string;
  /** Change this value to reload the list (e.g. after the document text was saved). */
  refreshKey?: unknown;
}

const DocumentImagesPanel: React.FC<Props> = ({ docId, refreshKey }) => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const [images, setImages] = React.useState<DocumentImageItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [busyIds, setBusyIds] = React.useState<number[]>([]);
  const [downloadingAll, setDownloadingAll] = React.useState(false);
  const [notice, setNotice] = React.useState("");

  const fetchImages = React.useCallback(() => {
    if (!docId) return Promise.resolve();
    setLoading(true);
    setError("");
    return axios
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

  React.useEffect(() => {
    fetchImages();
  }, [fetchImages, refreshKey]);

  // Remote images without a stored copy — the ones "pobierz do MinIO" applies to.
  const downloadable = images.filter((img) => img.id !== undefined && img.source_url && !img.is_local);

  const downloadImages = async (ids: number[] | null) => {
    setError("");
    setNotice("");
    if (ids) setBusyIds((current) => [...current, ...ids]);
    else setDownloadingAll(true);
    try {
      const response = await axios.post(
        `${apiUrl}/document/${docId}/images/download`,
        ids ? { image_ids: ids } : {},
        { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` }, timeout: 300000 },
      );
      const failed = (response.data.results ?? []).filter((r: any) => r.status === "error");
      setNotice(
        `Zapisano w MinIO: ${response.data.stored ?? 0}`
        + (failed.length ? `, błędy: ${failed.length} (${failed[0].message})` : "."),
      );
      await fetchImages();
    } catch (err: any) {
      setError(err.response?.data?.message || err.message || "Nie udało się pobrać obrazków.");
    } finally {
      if (ids) setBusyIds((current) => current.filter((id) => !ids.includes(id)));
      else setDownloadingAll(false);
    }
  };

  const buttonStyle: React.CSSProperties = {
    fontSize: "0.78em", padding: "2px 8px", borderRadius: 4, cursor: "pointer",
    border: "1px solid #94a3b8", background: "#fff", color: "#334155",
  };

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
          {notice && <div style={{ color: "#166534", fontSize: "0.85em", marginBottom: 6 }}>{notice}</div>}

          {downloadable.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <button
                type="button"
                style={{ ...buttonStyle, fontSize: "0.85em", padding: "3px 10px" }}
                disabled={downloadingAll || busyIds.length > 0}
                onClick={() => downloadImages(null)}
              >
                {downloadingAll
                  ? "Pobieram…"
                  : `📦 Pobierz wszystkie do MinIO (${downloadable.length})`}
              </button>
            </div>
          )}

          {images.length === 0 && !loading && !error && (
            <div style={{ color: "#64748b", fontSize: "0.88em" }}>Brak ilustracji.</div>
          )}

          {images.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              {images.map((img, idx) => (
                <figure key={img.id ?? `${img.position ?? idx}`} style={{ width: 160, margin: 0 }}>
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
                  {img.id !== undefined && img.source_url && !img.is_local && (
                    <button
                      type="button"
                      style={{ ...buttonStyle, marginTop: 4 }}
                      disabled={downloadingAll || busyIds.includes(img.id)}
                      onClick={() => downloadImages([img.id as number])}
                    >
                      {busyIds.includes(img.id) ? "Pobieram…" : "📦 Pobierz do MinIO"}
                    </button>
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
