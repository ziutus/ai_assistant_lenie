import axios from "axios";
import React from "react";

import {
  ai_correct_query,
  llm_simple_jobs_model_name,
} from "../viariables";
import {useSelector} from "react-redux";

export const useManageLLM = ({ formik }) => {
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [message, setMessage] = React.useState("");

  const apiUrl = useSelector((state) => state.api.apiServer);
  const apiKey = useSelector((state) => state.api.apiKey);

  const handleGetLinkByID = async (link_id) => {
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
      // await formik.setFieldValue("id", link_id);
      // console.log(website);
      await formik.setFormikState({
        values: { ...formik.values, ...response.data },
      });
      // setWebsite(response.data);
      setIsLoading(false);
      setIsError(false);
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

      console.log("Getting next document ID to correct");
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

      setMessage(response2.data.message);
      console.log(response2.data.message);
      console.log(response2.data);
      await handleGetLinkByID(response2.data["next_id"]);
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

      // handleClean();
      setMessage(response2.data.message);
      console.log(response2.data.message);
      console.log(response2.data);
      await handleGetLinkByID(response2.data["next_id"]);
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

  const handleCorrectUsingAI = async (website) => {
    setIsLoading(true);
    try {
      const response = await axios.post(
        `${apiUrl}/ai_ask`,
        {
          text: website.text,
          query: ai_correct_query,
          model: llm_simple_jobs_model_name,
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
      console.log("end of handleCorrectUsingAI");
    } catch (error) {
      console.error("There was an error on handleCorrectUsingAI!", error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 400
      ) {
        message += " Check your API key first";
      }
      setMessage(`There was an error on handleCorrectUsingAI: ${message}`);
      setIsLoading(false);
      setIsError(true);
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
    handleCorrectUsingAI,
    handleTranslate,
  };
};
