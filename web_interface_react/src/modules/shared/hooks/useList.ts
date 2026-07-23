import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

export const useList = () => {
  const [data, setData] = React.useState<any[] | null>(null);
  const [dataAllLength, setDataAllLength] = React.useState(0);
  const [message, setMessage] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const handleGetList = async (
    type: string,
    documentState: string,
    searchInDocument?: string,
    obsidianNotesFilter?: { onlyMissing?: boolean; onlyHas?: boolean },
    page = 1,
    pageSize = 100,
    withoutEmbedding = false,
  ) => {
    setIsLoading(true);
    try {
      const response = await axios.get(`${apiUrl}/website_list`, {
        headers: {
          "x-api-key": `${apiKey}`,
        },
        params: {
          type,
          processing_status: documentState,
          search_in_document: searchInDocument,
          only_missing_obsidian_notes: obsidianNotesFilter?.onlyMissing || undefined,
          only_has_obsidian_notes: obsidianNotesFilter?.onlyHas || undefined,
          page,
          limit: pageSize,
          without_embedding: withoutEmbedding || undefined,
        },
      });
      console.log(response.data.message);
      console.log(response.data);
      if (response.data.websites != null) {
        setData(response.data.websites);
      }
      setDataAllLength(response.data.all_results_count)
      console.log("end of handleGetList");
      setIsLoading(false);
      setIsError(false);
    } catch (error: any) {
      console.error("There was an error on handleGetList!", error);
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
      setMessage(`There was an error on suggesting handleGetList. ${message}`);
    }
  };

  return { message, isLoading, isError, data, handleGetList, dataAllLength };
};
