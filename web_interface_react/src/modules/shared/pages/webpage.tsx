import React from "react";
import { useFormik } from "formik";
import { useManageLLM } from "../hooks/useManageLLM";
import SharedInputs from "../components/SharedInputs/sharedInputs";
import InputsForAllExceptLink from "../components/SharedInputs/InputsForAllExceptLink";
import { useParams, NavLink } from "react-router-dom";
import FormButtons from "../components/FormButtons/formButtons";
import { AuthorizationContext } from '../context/authorizationContext';
import axios from "axios";

const Webpage = () => {
  const { id } = useParams();
  const { selectedDocumentType, selectedDocumentState, apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [panelBusy, setPanelBusy] = React.useState(false);
  const [reopening, setReopening] = React.useState(false);

  React.useEffect(() => {
    if (id) {
      handleGetLinkByID(id).then(() => null);
    }
  }, [id]);

  const formik: any = useFormik({
    initialValues: {
      id: "",
      byline: "",
      source: "",
      language: "",
      url: "",
      tags: "",
      title: "",
      document_type: "webpage",
      summary: "",
      text: "",
      text_md: "",
      processing_status: "",
      processing_error_code: "",
      chapter_list: "",
      note: "",
      ingested_at: "",
      published_on: "",
      published_on_method: "",
      next_id: null,
      previous_id: null,
      next_type: "",
      previous_type: "",
      embeddings_count: 0,
      approved_chunks_count: 0,
      analysis_run_id: null,
      analysis_chunks_count: 0,
      pending_chunks_count: 0,
      content_locked: false,
    },
    onSubmit: () => {},
  });

  const {
    message,
    isError,
    isLoading,
    autoFlowComplete,
    handleReturnToList,
    handleNextAfterAutoFlow,
    handleGetPageByUrl,
    handleSaveWebsiteNext,
    handleSaveWebsiteToCorrect,
    handleGetLinkByID,
    handleGetEntryToReview,
    handleRemoveNotNeededText
  } = useManageLLM({
    formik, selectedDocumentType, selectedDocumentState
  });

  const formatIngestedAt = (value: string | null | undefined) => {
    if (!value) return "brak danych";
    const parsed = new Date(value.includes("T") ? value : value.replace(" ", "T"));
    return Number.isNaN(parsed.getTime())
      ? value
      : parsed.toLocaleString("pl-PL", { dateStyle: "medium", timeStyle: "short" });
  };
  const publicationMethodLabels: Record<string, string> = {
    html: "metadane strony",
    llm: "analiza treści",
    manual: "ręcznie",
    relative: "data względna",
  };
  const contentLocked = Boolean(formik.values.content_locked || Number(formik.values.embeddings_count) > 0);
  const pageBusy = isLoading || panelBusy || reopening;
  const analysisChunksCount = Number(formik.values.analysis_chunks_count || 0);
  const pendingChunksCount = Number(formik.values.pending_chunks_count || 0);
  const hasAnalysis = analysisChunksCount > 0;
  const chunkActionLabel = pendingChunksCount > 0
    ? "Przejdź do przeglądu chunków"
    : analysisChunksCount === 1 && Number(formik.values.embeddings_count) > 0
      ? "Pokaż wynik analizy (1 chunk)"
      : "Pokaż wynik analizy";

  const reopenForEditing = async () => {
    if (!id || !window.confirm(
      "Otworzyć dokument ponownie do edycji? Chunki, embeddingi, encje i pozostałe analizy zostaną usunięte i trzeba będzie wykonać proces od początku.",
    )) return;
    setReopening(true);
    try {
      await axios.post(`${apiUrl}/document/${id}/reopen_editing`, {}, {
        headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` },
      });
      await handleGetLinkByID(id);
    } finally {
      setReopening(false);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: "10px" }}>
        <h2 style={{ margin: 0 }}>Webpage</h2>
        {id && (
          <div style={{
            display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center",
            padding: "5px 10px", border: "1px solid #e2e8f0",
            borderRadius: 6, background: "#f8fafc", fontSize: "0.84em", color: "#475569",
          }}>
            <span>
              Dodano do Lenie: <strong>{formatIngestedAt(formik.values.ingested_at)}</strong>
            </span>
            <span>
              Opublikowano: <strong>{formik.values.published_on || "nie wykryto"}</strong>
              {formik.values.published_on_method && (
                <small style={{ marginLeft: 5, color: "#64748b" }}>
                  ({publicationMethodLabels[formik.values.published_on_method]
                    ?? formik.values.published_on_method})
                </small>
              )}
            </span>
          </div>
        )}
        {id && hasAnalysis && (
          <NavLink
            className={"button"}
            to={`/chunks/${id}`}
            state={{ docType: "webpage" }}
            aria-disabled={pageBusy}
            onClick={(event) => { if (pageBusy) event.preventDefault(); }}
            style={{ fontSize: "0.85em", pointerEvents: pageBusy ? "none" : "auto", opacity: pageBusy ? 0.55 : 1 }}
          >
            {chunkActionLabel}
          </NavLink>
        )}
        {id && contentLocked && (
          <button type="button" className="button" onClick={reopenForEditing} disabled={pageBusy}>
            {reopening ? "Otwieram…" : "Otwórz ponownie do edycji"}
          </button>
        )}
      </div>
      <form onSubmit={formik.handleSubmit} style={{ width: "min(1600px, calc(100vw - 48px))", maxWidth: "100%" }}>
        {contentLocked && (
          <div style={{
            marginBottom: 12, padding: 10, borderRadius: 6,
            border: "1px solid #f59e0b", background: "#fffbeb", color: "#92400e",
          }}>
            Dokument ma embeddingi. Treść i dane pochodne są zablokowane. Aby ją zmienić,
            otwórz dokument ponownie do edycji i wykonaj cały proces od początku.
          </div>
        )}
        <fieldset disabled={pageBusy || contentLocked} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <SharedInputs
          formik={formik}
          isLoading={pageBusy || contentLocked}
          handleGetLinkByID={(id: any) => handleGetLinkByID(id, true)}
          handleGetEntryToReview={handleGetEntryToReview}
          handleGetPageByUrl={handleGetPageByUrl}
        />
        <InputsForAllExceptLink
          formik={formik}
          isLoading={pageBusy || contentLocked}
          onProcessingChange={setPanelBusy}
          handleRemoveNotNeededText={handleRemoveNotNeededText}
          showCleanText
        />

        {autoFlowComplete ? (
          <section style={{
            marginTop: 14, padding: 14, border: "1px solid #86efac",
            borderRadius: 8, background: "#f0fdf4",
          }}>
            <strong style={{ color: "#166534" }}>Dokument przetworzony automatycznie.</strong>
            <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button type="button" className="button" onClick={handleReturnToList}>
                Wróć do listy
              </button>
              <button type="button" className="button"
                onClick={() => handleNextAfterAutoFlow(formik.values)} disabled={isLoading}>
                {isLoading ? "Szukam…" : "Następny z listy"}
              </button>
              <NavLink className="button" to={`/chunks/${formik.values.id}`}>
                Pokaż utworzony chunk
              </NavLink>
            </div>
          </section>
        ) : (
          <FormButtons
            message={message}
            formik={formik}
            isError={isError}
            isLoading={pageBusy}
            handleSaveWebsiteNext={handleSaveWebsiteNext}
            handleSaveWebsiteToCorrect={handleSaveWebsiteToCorrect}
          />
        )}
        </fieldset>
      </form>
    </div>
  );
};

export default Webpage;
