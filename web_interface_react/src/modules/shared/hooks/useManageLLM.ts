import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";
import { useNavigate } from "react-router-dom";
import { describeRequestError } from "../utils/requestError";
import { probeBackend } from "../utils/backendProbe";

/** Size of what is about to be sent, in units a person can judge ("812 KB"). Never the content itself. */
const payloadSize = (payload: unknown): string => {
  try {
    const bytes = new Blob([JSON.stringify(payload ?? {})]).size;
    return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(2)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
  } catch {
    return "";
  }
};

const looksLikeRequestError = (error: any): boolean =>
  Boolean(error && (error.isAxiosError || error.config || error.response || error.code));

export const useManageLLM = ({ formik }: { formik: any; selectedDocumentType: string; selectedDocumentState: string }) => {
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [message, setMessage] = React.useState("");
  // Technical details belong to ONE message; once the message changes they are
  // stale and `errorDetails` below goes back to "".
  const [errorInfo, setErrorInfo] = React.useState({ message: "", details: "" });
  const [autoFlowComplete, setAutoFlowComplete] = React.useState(false);
  const { apiKey, apiUrl, apiType } = React.useContext(AuthorizationContext);
  const navigate = useNavigate();
  const errorDetails = errorInfo.message === message ? errorInfo.details : "";

  /**
   * One place that turns a failed request into the on-screen message (plain Polish
   * summary) plus the copyable technical block, so nobody has to ask the user what
   * the browser console said. When the server never answered, it also probes
   * `/healthz` to tell "backend/NAS down" from "only this request failed".
   * Returns the summary. See web_interface_react/AGENTS.md, "Error messages".
   */
  const reportRequestError = async (
    error: any,
    operation: string,
    startedAt: number,
    context: Record<string, string | number | null | undefined> = {},
  ): Promise<string> => {
    console.error(operation, error);
    let summary: string;
    let details: string;
    if (looksLikeRequestError(error)) {
      const status = error?.response?.status;
      const info = describeRequestError(error, operation, {
        startedAt,
        context: {
          ...context,
          Wskazówka: status === 400 || status === 401 || status === 403
            ? "Sprawdź klucz API w /connect (odmowa dostępu lub błędne żądanie)"
            : undefined,
        },
      });
      summary = info.summary;
      details = info.details;
      if (!error.response) {
        const probe = await probeBackend(String(apiUrl ?? ""));
        details += `\n${probe.join("\n")}`;
      }
    } else {
      // A failure raised by our own code (e.g. a background job reporting "failed"), not by the network.
      summary = `${operation}: ${error?.message ?? "nieznany błąd"}`;
      details = [
        `Operacja: ${operation}`,
        ...Object.entries(context)
          .filter(([, value]) => value !== null && value !== undefined && value !== "")
          .map(([key, value]) => `${key}: ${value}`),
        `Komunikat: ${error?.message ?? String(error)}`,
      ].join("\n");
    }
    setMessage(summary);
    setErrorInfo({ message: summary, details });
    return summary;
  };


  const handleGetLinkByID = async (link_id: string, redirect = false) => {
    setIsLoading(true);
    setAutoFlowComplete(false);
    // setLinkId(link_id);
    const startedAt = Date.now();
    try {
      const response = await axios.get(`${apiUrl}/website_get`, {
        params: {
          id: link_id,
        },
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "x-api-key": `${apiKey}`,
        },
      });

      setMessage("");
      console.log(response.data);
      console.log("cleaning values in webiste object");

      if (redirect) {
        navigate(`/${response.data.document_type}/${response.data.id}`);
      } else {
        // await formik.setFieldValue("id", link_id);
        // console.log(website);
        await formik.setFormikState({
          values: { ...formik.values, ...response.data },
        });
        // setWebsite(response.data);
        setIsLoading(false);
        setIsError(false);
      }
    } catch (error: any) {
      await reportRequestError(error, "Nie udało się pobrać dokumentu", startedAt, { Dokument: link_id });
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleGetPageByUrl = async (url: string) => {
    setIsLoading(true);
    if (url.length > 0) {
      const startedAt = Date.now();
      try {
        const response = await axios.post(
          `${apiUrl}/website_is_paid`,
          {
            url: url,
          },
          {
            headers: {
              "Content-Type": "application/x-www-form-urlencoded",
              "x-api-key": `${apiKey}`,
            },
          },
        );

        if (response.data.is_paid === false) {
          try {
            const response = await axios.post(
              `${apiUrl}/website_download_text_content`,
              {
                url: url,
              },
              {
                headers: {
                  "Content-Type": "application/x-www-form-urlencoded",
                  "x-api-key": `${apiKey}`,
                },
              },
            );
            // console.log(response.data.message)
            // console.log(response.data)

            formik.setFormikState({
              values: {
                ...formik.values,
                text: response.data.text,
                summary: response.data.summary,
                title: response.data.title,
                language: response.data.language,
              },
            });
            setMessage(response.data.message);
            console.log("end of checking if link handleGetLinkAll");
          } catch (error: any) {
            await reportRequestError(error, "Nie udało się pobrać treści strony", startedAt, { Adres: url });
          }
        } else {
          setMessage("Paid website, not downloaded");
        }
        setIsLoading(false);
        setIsError(false);
        setMessage("");
      } catch (error: any) {
        await reportRequestError(error, "Nie udało się sprawdzić strony", startedAt, { Adres: url });
        setIsLoading(false);
        setIsError(true);
      }
    }
  };

  const handleSaveWebsiteToCorrect = async (website: any) => {
    setIsLoading(true);
    var text_tmp = website.text;
    var text_tmp_md = website.text_md;
    if (website.document_type === "link") {
      text_tmp = "";
      text_tmp_md = "";
    }

    const startedAt = Date.now();
    const savePayload = {
      id: website.id,
      url: website.url,
      tags: website.tags,
      title: website.title,
      summary: website.summary,
      source: website.source,
      text: text_tmp,
      text_md: text_tmp_md,
      language: website.language,
      document_type: website.document_type,
      chapter_list: website.chapter_list,
      outline_md: website.outline_md,
      byline: website.byline,
      email_sender: website.email_sender,
      note: website.note,
    };
    try {
      const response = await axios.post(
        `${apiUrl}/website_save`,
        savePayload,
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );
      setMessage(response.data.message);
      console.log(response.data.message);
      console.log(response.data);
      setIsLoading(false);
      setIsError(false);
    } catch (error: any) {
      await reportRequestError(error, "Nie udało się zapisać dokumentu", startedAt, {
        Dokument: website.id,
        Typ: website.document_type,
        "Rozmiar zapisywanych danych": payloadSize(savePayload),
      });
      setIsLoading(false);
      setIsError(true);
    }
  };

  // `destination` only matters for YouTube: "ner" (default) continues to the per-chapter
  // NER review, "chunks" skips it and goes straight to the chunk analysis.
  const handleSaveWebsiteNext = async (website: any, destination: "ner" | "chunks" = "ner") => {
    setIsLoading(true);
    setAutoFlowComplete(false);

    var text_tmp = website.text;
    var text_tmp_md = website.text_md;
    if (website.document_type === "link") {
      text_tmp = "";
    }

    const startedAt = Date.now();
    try {
      const response = await axios.post(
        `${apiUrl}/website_save`,
        {
          id: website.id,
          url: website.url,
          tags: website.tags,
          title: website.title,
          summary: website.summary,
          source: website.source,
          text: text_tmp,
          text_md: text_tmp_md,
          language: website.language,
          document_type: website.document_type,
          // A reviewed webpage is ready for chunking, not yet for embeddings.
          // The YouTube flow opens the chunk review explicitly below, so keep
          // it in manual review until that analysis has been completed.
          processing_status: website.document_type === "webpage"
            ? "MD_SIMPLIFIED"
            : website.document_type === "youtube"
              ? "NEED_MANUAL_REVIEW"
            : "READY_FOR_EMBEDDING",
          chapter_list: website.chapter_list,
          outline_md: website.outline_md,
          byline: website.byline,
          email_sender: website.email_sender,
          note: website.note,
        },
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      if (website.document_type === "webpage") {
        const preview = await axios.post(
          `${apiUrl}/document/${website.id}/split_preview?mode=article&chunk_size=5000`,
          { text: text_tmp_md || text_tmp || "" },
          { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` } },
        );
        const isSingleChunk = preview.data.chunk_count === 1;
        const analysis = await axios.post(
          `${apiUrl}/document/${website.id}/analyze_chunks`,
          {
            mode: "article",
            chunk_size: 5000,
            split_only: true,
            enrich_document: true,
            auto_finalize_single: isSingleChunk,
          },
          { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` } },
        );
        if (isSingleChunk) {
          const jobId = analysis.data.job_id;
          if (!jobId) throw new Error("Backend nie zwrócił identyfikatora automatycznego zadania");
          for (let attempt = 0; attempt < 240; attempt += 1) {
            const jobResponse = await axios.get(`${apiUrl}/analysis_job/${jobId}`, {
              headers: { "x-api-key": `${apiKey}` },
            });
            const job = jobResponse.data.job;
            setMessage(job?.progress || "Automatyczne przetwarzanie dokumentu…");
            if (job?.status === "done") {
              setMessage("Dokument zatwierdzony. Utworzono chunk i embedding.");
              setIsLoading(false);
              setIsError(false);
              setAutoFlowComplete(true);
              return;
            }
            if (job?.status === "failed") {
              throw new Error(job.error || "Automatyczne przetwarzanie nie powiodło się");
            }
            await new Promise(resolve => window.setTimeout(resolve, 1500));
          }
          // The job is persistent and keeps running on the backend.  Do not
          // report a failed save merely because this page stopped waiting;
          // /chunks resumes monitoring the same job after navigation.
          setMessage("Dokument zapisany; automatyczne przetwarzanie nadal trwa.");
          setIsLoading(false);
          setIsError(false);
          navigate(`/chunks/${website.id}`);
          return;
        }
        setMessage(response.data.message);
        setIsLoading(false);
        setIsError(false);
        // NER is available in the editor; this action continues to chunk review.
        navigate(`/chunks/${website.id}`);
        return;
      }

      if (website.document_type === "youtube") {
        setMessage(response.data.message);
        setIsLoading(false);
        setIsError(false);
        // NER review is per chapter: land on the first content chapter (position 1), not the whole document.
        navigate(destination === "chunks" ? `/chunks/${website.id}` : `/ner/${website.id}/1`);
        return;
      }

      console.log("Getting next document ID to correct");
      console.log("id: " + website.id);
      console.log("document_type: " + website.document_type);
      console.log("processing_status: " + website.processing_status);

      const response2 = await axios.get(
        `${apiUrl}/website_get_next_to_correct`,
        {
          params: {
            id: website.id,
          },
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      console.log(response2.data)

      setMessage(response2.data.message);
      navigate(`/${response2.data.next_type}/${response2.data.next_id}`);
      // console.log(response2.data.message);
      // console.log(response2.data);
      // await handleGetLinkByID(response2.data["next_id"]);
      setIsLoading(false);
      setIsError(false);
    } catch (error: any) {
      await reportRequestError(error, "Nie udało się zapisać dokumentu i przejść dalej", startedAt, {
        Dokument: website.id,
        Typ: website.document_type,
        "Rozmiar tekstu": payloadSize({ text: text_tmp, text_md: text_tmp_md }),
      });
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleReturnToList = () => {
    setAutoFlowComplete(false);
    navigate("/list");
  };

  const handleNextAfterAutoFlow = async (website: any) => {
    setIsLoading(true);
    const startedAt = Date.now();
    try {
      const response = await axios.get(`${apiUrl}/website_get_next_to_correct`, {
        params: {
          id: website.id,
        },
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "x-api-key": `${apiKey}`,
        },
      });
      setAutoFlowComplete(false);
      if (response.data.next_id && response.data.next_type) {
        navigate(`/${response.data.next_type}/${response.data.next_id}`);
      } else {
        navigate("/list");
      }
    } catch (error: any) {
      setIsError(true);
      await reportRequestError(error, "Nie udało się pobrać następnego dokumentu", startedAt, { Dokument: website.id });
    } finally {
      setIsLoading(false);
    }
  };

  const handleGetEntryToReview = async (website: any) => {
    console.log("Getting first document ID to correct");
    setIsLoading(true);
    let document_id: string | number;
    if (website.id > 0) {
      document_id = website.id;
    } else {
      document_id = 1;
    }

    const startedAt = Date.now();
    try {
      const response2 = await axios.get(
        `${apiUrl}/website_get_next_to_correct`,
        {
          params: {
            id: document_id,
          },
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      setMessage(response2.data.message);
      navigate(`/${response2.data.next_type}/${response2.data.next_id}`);
      setIsLoading(false);
      setIsError(false);
    } catch (error: any) {
      await reportRequestError(error, "Nie udało się pobrać dokumentu do przeglądu", startedAt, { Dokument: document_id });
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleRemoveNotNeededText = async (website: any) => {
    setIsLoading(true);
    const startedAt = Date.now();
    try {
      const response = await axios.post(
          `${apiUrl}/website_text_remove_not_needed`,
          {
            url: website.url,
            text: website.text,
          },
          {
            headers: {
              "Content-Type": "application/x-www-form-urlencoded",
              "x-api-key": `${apiKey}`,
            },
          }
      );
      formik.setFormikState({
        values: { ...formik.values, text: response.data.text },
      });
      setIsLoading(false);
      setIsError(false);
      console.log("end of handleRemoveNotNeededText");
    } catch (error: any) {
      await reportRequestError(error, "Nie udało się usunąć zbędnego tekstu", startedAt, {
        Dokument: website.id,
        "Rozmiar tekstu": payloadSize(website.text),
      });
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleDeleteDocumentNext = async (website: any) => {
    setIsLoading(true);

    const startedAt = Date.now();
    try {
      const response = await axios.delete(
        `${apiUrl}/website_delete`,
        {
          params: {
            id: website.id,
          },
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      // formik.resetForm();

      console.log("Getting next document ID to correct");
      console.log("id: " + website.id);
      console.log("document_type: " + website.document_type);
      console.log("processing_status: " + website.processing_status);

      const response2 = await axios.get(
        `${apiUrl}/website_get_next_to_correct`,
        {
          params: {
            id: website.id,
          },
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      console.log(response2.data)

      setMessage(response2.data.message);
      navigate(`/${response2.data.next_type}/${response2.data.next_id}`);
      // console.log(response2.data.message);
      // console.log(response2.data);
      setIsLoading(false);
      setIsError(false);
    } catch (error: any) {
      await reportRequestError(error, "Nie udało się usunąć dokumentu", startedAt, { Dokument: website.id });
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleYoutubeRetryCaptions = async (
    document_id: string | number,
    options: { localMessage?: boolean } = {},
  ) => {
    setIsLoading(true);
    const startedAt = Date.now();
    try {
      const response = await axios.post(
        `${apiUrl}/website_youtube_retry_captions`,
        { id: document_id },
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );
      setMessage(response.data.message);
      setIsLoading(false);
      setIsError(false);
      return response.data;
    } catch (error: any) {
      const message = error.response?.data?.message || error.message;
      if (options.localMessage) {
        console.error("There was an error on handleYoutubeRetryCaptions!", error);
      } else {
        await reportRequestError(error, "Nie udało się ponowić pobierania napisów YouTube", startedAt, { Dokument: document_id });
      }
      setIsLoading(false);
      setIsError(true);
      return { error: message };
    }
  };

  const handleDeleteDocument = async (document_id: string) => {
    setIsLoading(true);
    console.log("Deleting document with id: " + document_id);

    const startedAt = Date.now();
    try {
      const response = await axios.delete(
        `${apiUrl}/website_delete`,
        {
          params: {
            id: document_id,
          },
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      setIsLoading(false);
      setIsError(false);
    } catch (error: any) {
      await reportRequestError(error, "Nie udało się usunąć dokumentu", startedAt, { Dokument: document_id });
      setIsLoading(false);
      setIsError(true);
    }
  };

  // Turn a `link` document into a `webpage` in place: the backend fetches the
  // page (or fails for a paywall/login page) and queues content extraction.
  const handlePromoteToWebpage = async (website: any) => {
    setIsLoading(true);
    setAutoFlowComplete(false);
    setMessage("");
    const startedAt = Date.now();
    try {
      await axios.post(
        `${apiUrl}/document/${website.id}/promote_to_webpage`,
        {},
        {
          headers: {
            "Content-Type": "application/json",
            "x-api-key": `${apiKey}`,
          },
        },
      );
      setIsError(false);
      setMessage("Zmieniono w webpage. Trwa pobieranie treści…");
      // Re-reads /website_get and navigates to /webpage/:id (type is now webpage).
      await handleGetLinkByID(String(website.id), true);
    } catch (error: any) {
      setIsError(true);
      const reason = error?.response?.data?.reason;
      if (reason === "paywall") {
        setMessage("Nie można pobrać: strona jest za paywallem.");
      } else if (reason === "requires_login") {
        setMessage("Nie można pobrać: strona wymaga logowania.");
      } else if (reason === "download_failed") {
        setMessage("Nie udało się pobrać treści strony.");
      } else {
        await reportRequestError(error, "Nie udało się zmienić w webpage", startedAt, { Dokument: website.id });
      }
    } finally {
      setIsLoading(false);
    }
  };


  return {
    message,
    errorDetails,
    isError,
    isLoading,
    autoFlowComplete,
    handleReturnToList,
    handleNextAfterAutoFlow,
    handleGetPageByUrl,
    handlePromoteToWebpage,
    handleSaveWebsiteNext,
    handleSaveWebsiteToCorrect,
    handleGetLinkByID,
    handleGetEntryToReview,
    handleRemoveNotNeededText,
    handleDeleteDocumentNext,
    handleDeleteDocument,
    handleYoutubeRetryCaptions
  };
};
