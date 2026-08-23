import React from "react";
import axios from "axios";
import { useFormik } from "formik";
import { useManageLLM } from "../hooks/useManageLLM";
import SharedInputs from "../components/SharedInputs/sharedInputs";
import InputsForAllExceptLink from "../components/SharedInputs/InputsForAllExceptLink";
import { NavLink, useParams } from "react-router-dom";
import FormButtons from "../components/FormButtons/formButtons";
import { AuthorizationContext } from '../context/authorizationContext';
import { markCaptionsFetching, isCaptionsFetching } from "../utils/youtubeCaptionsFetchStatus";


const Youtube = () => {
  const { id } = useParams();
  const { selectedDocumentType, selectedDocumentState, apiKey, apiUrl } = React.useContext(AuthorizationContext);

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
      document_type: "youtube",
      summary: "",
      text: "",
      processing_status: "",
      processing_error_code: "",
      chapter_list: "",
      note: "",
      next_id: null,
      previous_id: null,
      next_type: "",
      previous_type: "",
    },
    onSubmit: () => {},
  });

  const {
    message,
    isError,
    isLoading,
    handleGetPageByUrl,
    handleSaveWebsiteNext,
    handleSaveWebsiteToCorrect,
    handleGetLinkByID,
    handleGetEntryToReview,
    handleRemoveNotNeededText,
    handleYoutubeRetryCaptions,
  } = useManageLLM({
    formik, selectedDocumentType, selectedDocumentState
  });

  const transcriptMissing = !String(formik.values.text || "").trim();
  // Paragraphization is deliberately constrained to imported Markdown
  // chapters, so the model can only add whitespace within a known section.
  const hasMarkdownChapters = /^#{1,2} .+/m.test(String(formik.values.text || ""));
  const canFetchCaptions = Boolean(id) && transcriptMissing
    && ["URL_ADDED", "NEED_TRANSCRIPTION", "TEMPORARY_ERROR"].includes(formik.values.processing_status);
  const [captionMessage, setCaptionMessage] = React.useState("");
  const [paragraphizing, setParagraphizing] = React.useState(false);
  const [paragraphMessage, setParagraphMessage] = React.useState("");
  // Covers the case where the fetch was triggered from /list (or another tab)
  // and this page was opened while it's still running — see
  // utils/youtubeCaptionsFetchStatus.ts for why a plain isLoading flag here
  // isn't enough.
  const [fetchingElsewhere, setFetchingElsewhere] = React.useState(false);

  React.useEffect(() => {
    if (!id || !isCaptionsFetching(id)) {
      setFetchingElsewhere(false);
      return;
    }
    setFetchingElsewhere(true);
    const interval = setInterval(() => {
      if (!isCaptionsFetching(id)) {
        clearInterval(interval);
        setFetchingElsewhere(false);
        handleGetLinkByID(id).then(() => null);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [id]);

  const fetchCaptions = async () => {
    if (!id) return;
    setCaptionMessage("");
    markCaptionsFetching(id, true);
    let result;
    try {
      result = await handleYoutubeRetryCaptions(id, { localMessage: true });
    } finally {
      markCaptionsFetching(id, false);
    }
    if ("error" in result) {
      setCaptionMessage(`Nie udało się pobrać napisów: ${result.error}`);
      return;
    }
    await handleGetLinkByID(id);
    if (result.processing_status === "NEED_MANUAL_REVIEW") {
      setCaptionMessage("Napisy zostały pobrane przez Webshare. Transkrypcja jest gotowa do przeglądu.");
    } else {
      setCaptionMessage(`Nie pobrano transkrypcji. Stan: ${result.processing_status}${result.processing_error_code ? ` (${result.processing_error_code})` : ""}.`);
    }
  };

  const paragraphizeTranscript = async () => {
    if (!hasMarkdownChapters) return;
    if (!id || !window.confirm("Podzielić transkrypcję na akapity tematyczne przy użyciu Bielika? Tekst nie będzie parafrazowany.")) return;
    setParagraphizing(true);
    setParagraphMessage("");
    try {
      const response = await axios.post(
        `${apiUrl}/document/${id}/paragraphize_transcript`,
        {},
        {
          headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` },
          timeout: 240000,
        },
      );
      await handleGetLinkByID(id);
      setParagraphMessage(`Gotowe: ${response.data.paragraph_count} akapitów w ${response.data.chapter_count} rozdziałach (${response.data.model_calls} wywołań Bielika).`);
    } catch (error: any) {
      const detail = error.response?.data?.message || error.message;
      setParagraphMessage(`Nie udało się podzielić transkrypcji: ${detail}`);
    } finally {
      setParagraphizing(false);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Youtube</h2>
      {id && <NavLink to={`/llm-costs?document_id=${id}`} style={{ display: "inline-block", marginBottom: 10, fontSize: "0.9em", color: "#0369a1" }}>💰 Koszty i etapy LLM</NavLink>}
      <form onSubmit={formik.handleSubmit} style={{ maxWidth: "800px" }}>
        {id && transcriptMissing && (
          <section style={{ marginBottom: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}>
            <strong>Transkrypcja nie jest jeszcze dostępna.</strong>
            <div style={{ marginTop: 6, color: "#475569" }}>
              Stan: {formik.values.processing_status || "brak"}
              {formik.values.processing_error_code && ` · ${formik.values.processing_error_code}`}
            </div>
            {fetchingElsewhere ? (
              <div style={{ marginTop: 10, color: "#0369a1" }}>⏳ Pobieram napisy… (uruchomione z listy dokumentów)</div>
            ) : canFetchCaptions && (
              <button type="button" className="button" style={{ marginTop: 10 }} onClick={fetchCaptions} disabled={isLoading}>
                {isLoading
                  ? "Pobieram napisy…"
                  : formik.values.processing_status === "URL_ADDED"
                    ? "Pobierz transkrypcję (napisy przez Webshare)"
                    : "Spróbuj pobrać napisy ponownie"}
              </button>
            )}
            {captionMessage && <div style={{ marginTop: 8 }}>{captionMessage}</div>}
          </section>
        )}
        {id && !transcriptMissing && (
          <section style={{ marginBottom: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}>
            <strong>Formatowanie transkrypcji</strong>
            <div style={{ marginTop: 6, color: "#475569" }}>
              Bielik wskaże granice akapitów w obrębie istniejących rozdziałów. Zmieni wyłącznie odstępy między zdaniami.
            </div>
            {!hasMarkdownChapters && (
              <div role="status" style={{ marginTop: 8, color: "#92400e" }}>
                Nie można jeszcze podzielić transkrypcji na akapity: nie ma w niej rozdziałów. Rozdziały są importowane z ręcznie podanej listy czasowej albo z co najmniej dwóch znaczników czasu w opisie filmu YouTube. Ten film nie dostarcza żadnego z tych źródeł.
              </div>
            )}
            <button type="button" className="button" style={{ marginTop: 10 }} onClick={paragraphizeTranscript} disabled={!hasMarkdownChapters || paragraphizing || isLoading}>
              {paragraphizing ? "Dzielę na akapity…" : "Podziel transkrypcję na akapity (Bielik)"}
            </button>
            {paragraphMessage && <div style={{ marginTop: 8 }}>{paragraphMessage}</div>}
          </section>
        )}
        <SharedInputs
          formik={formik}
          isLoading={isLoading}
          handleGetLinkByID={(id: any) => handleGetLinkByID(id, true)}
          handleGetEntryToReview={handleGetEntryToReview}
          handleGetPageByUrl={handleGetPageByUrl}
        />
        <InputsForAllExceptLink
          formik={formik}
          isLoading={isLoading}
          handleRemoveNotNeededText={handleRemoveNotNeededText}
        />
        <FormButtons
          message={message}
          formik={formik}
          isError={isError}
          isLoading={isLoading}
          handleSaveWebsiteNext={handleSaveWebsiteNext}
          handleSaveWebsiteToCorrect={handleSaveWebsiteToCorrect}
        />
      </form>
    </div>
  );
};

export default Youtube;
