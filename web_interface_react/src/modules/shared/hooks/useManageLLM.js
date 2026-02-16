import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";
import { useNavigate } from "react-router-dom";


export const useManageLLM = ({ formik, selectedDocumentType, selectedDocumentState }) => {
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const { apiKey, apiUrl, apiType } = React.useContext(AuthorizationContext);
  const navigate = useNavigate();


  const handleGetLinkByID = async (link_id, redirect = false) => {
    setIsLoading(true);
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
    } catch (error) {
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

  const handleGetPageByUrl = async (url) => {
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
          } catch (error) {
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
      } catch (error) {
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

  const handleSaveWebsiteToCorrect = async (website) => {
    setIsLoading(true);
    var text_tmp = website.text;
    var text_tmp_md = website.text_md;
    var text_tmp_english = website.text_english;
    if (website.document_type === "link") {
      text_tmp = "";
      text_tmp_md = "";
      text_tmp_english = "";
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
          text_english: text_tmp_english,
          language: website.language,
          document_type: website.document_type,
          document_state: website.document_state,
          chapter_list: website.chapter_list,
          author: website.author,
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
    } catch (error) {
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

  const handleSaveWebsiteNext = async (website) => {
    setIsLoading(true);

    var text_tmp = website.text;
    var text_tmp_md = website.text_md;
    var text_tmp_english = website.text_english;
    if (website.document_type === "link") {
      text_tmp = "";
      text_tmp_english = "";
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
          text_english: text_tmp_english,
          language: website.language,
          document_type: website.document_type,
          document_state: "READY_FOR_TRANSLATION",
          chapter_list: website.chapter_list,
          author: website.author,
          note: website.note,
        },
        {
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
      console.log("document_state: " + website.document_state);

      const response2 = await axios.get(
        `${apiUrl}/website_get_next_to_correct`,
        {
          params: {
            id: website.id,
            document_type: selectedDocumentType,
            document_state: selectedDocumentState
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
    } catch (error) {
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

  const handleGetEntryToReview = async (website) => {
    console.log("Getting first document ID to correct");
    setIsLoading(true);
    let website_id;
    if (website.id > 0) {
      website_id = website.id;
    } else {
      website_id = 1;
    }

    try {
      const response2 = await axios.get(
        `${apiUrl}/website_get_next_to_correct`,
        {
          params: {
            id: website_id,
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
    } catch (error) {
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

  const handleSplitTextForEmbedding = async (website) => {
    setIsLoading(true);
    try {
      const response = await axios.post(
        `${apiUrl}/website_split_for_embedding`,
        {
          chapter_list: website.chapter_list,
          text: `${website.text}`,
        },
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );
      formik.setFormikState({
        values: { ...formik.values, text: response.data.text },
      });
      setIsLoading(false);
      setIsError(false);
      console.log("end of handleSplitTextForEmbedding");
    } catch (error) {
      console.error(
        "There was an error on handleSplitTextForEmbedding!",
        error,
      );
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setMessage(
        `There was an error on handleSplitTextForEmbedding: ${message}`,
      );
      setIsError(true);
      setIsLoading(false);
    }
  };

  const handleTranslate = async (website) => {
    setIsLoading(true);
    try {
      const response = await axios.post(
        `${apiUrl}/translate`,
        {
          text: website.text,
          target_language: "en",
          source_language: "pl",
        },
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );
      formik.setFormikState({
        values: { ...formik.values, text_english: response.data.message },
      });
      setIsLoading(false);
      setIsError(false);
      console.log("end of handleTranslate");
    } catch (error) {
      console.error("There was an error on handleTranslate!", error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setMessage(`There was an error on handleTranslate: ${message}`);
      setIsLoading(false);
      setIsError(true);
    }
  };

  const handleRemoveNotNeededText = async (website) => {
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
    } catch (error) {
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

  const handleDeleteDocumentNext = async (website) => {
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
      console.log("document_state: " + website.document_state);

      const response2 = await axios.get(
        `${apiUrl}/website_get_next_to_correct`,
        {
          params: {
            id: website.id,
            document_type: selectedDocumentType,
            document_state: selectedDocumentState
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
    } catch (error) {
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

  const handleDeleteDocument = async (website_id) => {
    setIsLoading(true);
    console.log("Deleting document with id: " + website_id);

    try {
      const response = await axios.get(
        `${apiUrl}/website_delete`,
        {
          params: {
            id: website_id,
          },
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      setIsLoading(false);
      setIsError(false);
    } catch (error) {
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
    handleGetPageByUrl,
    handleSaveWebsiteNext,
    handleSaveWebsiteToCorrect,
    handleGetLinkByID,
    handleGetEntryToReview,
    handleSplitTextForEmbedding,
    handleTranslate,
    handleRemoveNotNeededText,
    handleDeleteDocumentNext,
    handleDeleteDocument
  };
};

