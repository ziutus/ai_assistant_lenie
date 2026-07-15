import React from "react";
import {AuthorizationContext} from "../context/authorizationContext";
import axios from "axios";

export const useSearch = ({ callback }: { callback: () => void }) => {
  const [data, setData] = React.useState<any[] | null>(null);
  const [message, setMessage] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [results, setResults] = React.useState<any[] | null>(null);
  const [searchSimilar, setSearchSimilar] = React.useState('');

  const handleSearchSimilar = async (search?: string, searchLimit?: string, translate?: boolean) => {
    setIsLoading(true);
    console.log("searching: " + search)
    console.log("searching limit: " + searchLimit)
    console.log("translate: " + translate);

    // AWS Serverless two-step flow (ai_embedding_get + website_similar) removed
    // 2026-07-04 — the AWS document API is decommissioned.
    {
      try {
        const response = await axios.post(`${apiUrl}/website_similar`, {
          model: "amazon.titan-embed-text-v1",
          search: search,
          limit: searchLimit,
          translate: translate
        }, {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'x-api-key': `${apiKey}`,
          },
        });
        console.log(response.data.message);
        console.log(response.data);
        if (response.data.websites != null) {
          setData(response.data.websites);
          setResults(response.data.websites)
        }
        console.log("end of handleSearchSimilar2");
        setIsLoading(false);
        setIsError(false);
      } catch (error: any) {
        console.error("There was an error on handleGetList2!", error);
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
        setMessage(`There was an error on handleSearchSimilar2. ${message}`);
      }
    }
  };



  return { isError, isLoading, results, setResults, message, setMessage, handleSearchSimilar };
};
