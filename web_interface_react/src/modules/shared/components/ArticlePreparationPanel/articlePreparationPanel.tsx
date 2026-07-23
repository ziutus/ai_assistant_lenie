import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";

interface CleanupPreview {
  before_length: number;
  after_length: number;
  removed_line_count: number;
  removed_lines_preview: string[];
  portal: string | null;
  source_field: string;
}

const ArticlePreparationPanel = ({ formik }: { formik: any }) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [preview, setPreview] = React.useState<CleanupPreview | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState("");
  const headers = React.useMemo(() => ({
    "x-api-key": `${apiKey ?? ""}`,
    "Content-Type": "application/json",
  }), [apiKey]);

  const loadPreview = React.useCallback(async () => {
    if (!formik.values.id) return;
    try {
      const response = await axios.post(
        `${apiUrl}/document/${formik.values.id}/reclean_preview`,
        { save: false }, { headers },
      );
      setPreview(response.data);
    } catch {
      setPreview(null);
    }
  }, [apiUrl, formik.values.id, headers]);

  React.useEffect(() => { void loadPreview(); }, [loadPreview]);

  const refreshDocument = async () => {
    const response = await axios.get(`${apiUrl}/website_get`, {
      params: { id: formik.values.id }, headers,
    });
    formik.setFormikState({ values: { ...formik.values, ...response.data } });
  };

  const saveCleanup = async () => {
    if (!window.confirm("Zapisać oczyszczony Markdown jako kanoniczną treść artykułu?")) return;
    setBusy("cleanup"); setMessage("");
    try {
      const response = await axios.post(
        `${apiUrl}/document/${formik.values.id}/reclean_preview`,
        { save: true }, { headers },
      );
      await refreshDocument();
      setPreview(response.data);
      setMessage(`Zapisano Markdown: ${response.data.before_length} → ${response.data.after_length} znaków.`);
    } catch { setMessage("Nie udało się zapisać oczyszczonego artykułu."); }
    finally { setBusy(null); }
  };

  const extract = async (kind: "author" | "date") => {
    setBusy(kind); setMessage("");
    const endpoint = kind === "author" ? "extract_author" : "extract_publication_date";
    try {
      const response = await axios.post(
        `${apiUrl}/document/${formik.values.id}/${endpoint}`, {}, { headers },
      );
      if (kind === "author" && response.data.byline) {
        formik.setFieldValue("byline", response.data.byline);
        setMessage(`Autor: ${response.data.byline} (${response.data.byline_method}).`);
      } else if (kind === "date" && response.data.published_on) {
        formik.setFieldValue("published_on", response.data.published_on);
        setMessage(`Data publikacji: ${response.data.published_on} (${response.data.published_on_method}).`);
      } else {
        setMessage(kind === "author" ? "Nie znaleziono autora." : "Nie znaleziono daty publikacji.");
      }
    } catch { setMessage("Ekstrakcja metadanych nie powiodła się."); }
    finally { setBusy(null); }
  };

  if (!formik.values.id) return null;
  const changed = !!preview && preview.before_length !== preview.after_length;
  return (
    <section style={{ border: "1px solid #cbd5e1", borderRadius: 6, padding: 12, marginBottom: 14 }}>
      <strong>Przygotowanie artykułu</strong>
      <p style={{ margin: "6px 0", color: "#475569" }}>
        Ten etap działa niezależnie od chunków. Kanoniczną treścią strony jest Markdown.
      </p>
      {preview && (
        <div style={{ fontSize: "0.9em", marginBottom: 8 }}>
          Źródło: <code>{preview.source_field}</code> · portal: {preview.portal ?? "nierozpoznany"} · {preview.before_length} → {preview.after_length} znaków
          {changed ? ` · do usunięcia: ${preview.removed_line_count} linii` : " · bez zmian"}
          {preview.removed_lines_preview.length > 0 && (
            <details><summary>Przykładowe usuwane elementy</summary>
              <pre style={{ whiteSpace: "pre-wrap" }}>{preview.removed_lines_preview.join("\n")}</pre>
            </details>
          )}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="button" onClick={loadPreview} disabled={!!busy}>Sprawdź czyszczenie</button>
        <button type="button" className="button" onClick={saveCleanup} disabled={!!busy || !preview}>
          {busy === "cleanup" ? "Czyszczę…" : "Zapisz oczyszczony Markdown"}
        </button>
        <button type="button" className="button" onClick={() => extract("author")} disabled={!!busy}>
          {busy === "author" ? "Szukam…" : "Znajdź autora"}
        </button>
        <button type="button" className="button" onClick={() => extract("date")} disabled={!!busy}>
          {busy === "date" ? "Szukam…" : "Znajdź datę"}
        </button>
      </div>
      {formik.values.published_on && <div style={{ marginTop: 7 }}>Data publikacji: {formik.values.published_on}</div>}
      {message && <div style={{ marginTop: 7 }}>{message}</div>}
    </section>
  );
};

export default ArticlePreparationPanel;
