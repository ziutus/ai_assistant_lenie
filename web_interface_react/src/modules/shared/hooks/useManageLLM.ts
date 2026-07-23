import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";
import { useNavigate } from "react-router-dom";


export const useManageLLM = ({ formik, selectedDocumentType, selectedDocumentState }: { formik: any; selectedDocumentType: string; selectedDocumentState: string }) => {
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [autoFlowComplete, setAutoFlowComplete] = React.useState(false);
  const { apiKey, apiUrl, apiType } = React.useContext(AuthorizationContext);
  const navigate = useNavigate();


  const handleGetLinkByID = async (link_id: string, redirect = false) => {
    setIsLoading(true);
    setAutoFlowComplete(false);
    // setLinkId(link_id);
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
      console.error(error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setMessage(`Error on handleGetLinkByID ${message}`);
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleGetPageByUrl = async (url: string) => {
    setIsLoading(true);
    if (url.length > 0) {
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
            console.error("There was an error on handleGetLinkAll!", error);
            let message = error.message;
            if (error.response.status === 400) {
              message += " Check your API key first";
            }
            setMessage(`There was an error on handleGetLinkAll. ${message}`);
          }
        } else {
          setMessage("Paid website, not downloaded");
        }
        setIsLoading(false);
        setIsError(false);
        setMessage("");
      } catch (error: any) {
        setIsLoading(false);
        setIsError(true);

        console.error("There was an error on handleGetLinkAll!", error);
        let message = error.message;
        if (
          error.response &&
          error.response.status &&
          error.response.status === 400
        ) {
          message += " Check your API key first";
        }
        setMessage(`There was an error on handleGetLinkAll. ${message}`);
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
          chapter_list: website.chapter_list,
          byline: website.byline,
          note: website.note,
        },
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
      setIsLoading(false);
      setIsError(true);
      console.error("There was an error saving the data!", error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setMessage(`There was an error saving the data: ${message}`);
    }
  };

  const handleSaveWebsiteNext = async (website: any) => {
    setIsLoading(true);
    setAutoFlowComplete(false);

    var text_tmp = website.text;
    var text_tmp_md = website.text_md;
    if (website.document_type === "link") {
      text_tmp = "";
    }

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
          processing_status: website.document_type === "webpage"
            ? "MD_SIMPLIFIED"
            : "READY_FOR_EMBEDDING",
          chapter_list: website.chapter_list,
          byline: website.byline,
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
          throw new Error("Przekroczono czas oczekiwania na automatyczne przetwarzanie");
        }
        setMessage(response.data.message);
        setIsLoading(false);
        setIsError(false);
        navigate(`/chunks/${website.id}`, { state: { docType: "webpage" } });
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
            document_type: selectedDocumentType,
            processing_status: selectedDocumentState
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
      console.error("There was an error saving the data!", error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setIsLoading(false);
      setIsError(true);
      setMessage(`There was an error saving the data: ${message}`);
    }
  };

  const handleReturnToList = () => {
    setAutoFlowComplete(false);
    navigate("/list");
  };

  const handleNextAfterAutoFlow = async (website: any) => {
    setIsLoading(true);
    try {
      const response = await axios.get(`${apiUrl}/website_get_next_to_correct`, {
        params: {
          id: website.id,
          document_type: selectedDocumentType,
          processing_status: selectedDocumentState,
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
      setMessage(`Nie udało się pobrać następnego dokumentu: ${error.message}`);
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
      console.error("There was an error on handleGetEntryToReview!");
      console.error(error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setMessage(`There was an error on handleGetEntryToReview: ${message}`);
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleRemoveNotNeededText = async (website: any) => {
    setIsLoading(true);
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
      console.error("There was an error on handleRemoveNotNeededText!", error);
      let message = error.message;
      if (
          error.response &&
          error.response.status &&
          error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setMessage(`There was an error on handleRemoveNotNeededText: ${message}`);
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleDeleteDocumentNext = async (website: any) => {
    setIsLoading(true);

    try {
      const response = await axios.get(
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
            document_type: selectedDocumentType,
            processing_status: selectedDocumentState
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
      console.error("There was an error saving the data!", error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setIsLoading(false);
      setIsError(true);
      setMessage(`There was an error saving the data: ${message}`);
    }
  };

  const handleYoutubeRetryCaptions = async (document_id: string | number) => {
    setIsLoading(true);
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
      console.error("There was an error on handleYoutubeRetryCaptions!", error);
      const message = error.response?.data?.message || error.message;
      setMessage(`There was an error retrying YouTube captions: ${message}`);
      setIsLoading(false);
      setIsError(true);
      return null;
    }
  };

  const handleDeleteDocument = async (document_id: string) => {
    setIsLoading(true);
    console.log("Deleting document with id: " + document_id);

    try {
      const response = await axios.get(
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
      console.error("There was an error saving the data!", error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setIsLoading(false);
      setIsError(true);
      setMessage(`There was an error saving the data: ${message}`);
    }
  };


  return {
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
    handleRemoveNotNeededText,
    handleDeleteDocumentNext,
    handleDeleteDocument,
    handleYoutubeRetryCaptions
  };
};
