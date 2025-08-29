import React from "react";
import {AuthorizationContext} from "../context/authorizationContext";
import axios from "axios";

export const useSearch = ({ callback }) => {
  const [data, setData] = React.useState(null);
  const [message, setMessage] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const { apiKey, apiUrl, apiType } = React.useContext(AuthorizationContext);
  const [results, setResults] = React.useState(null);
  const [searchSimilar, setSearchSimilar] = React.useState('');

  React.useEffect(() => {
    handleSearchSimilar().then(() => null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  const handleSearchSimilar = async (search, searchLimit, translate) => {
    setIsLoading(true);
    console.log("api Type:" + apiType)
    console.log("searching: " + search)
    console.log("searching limit: " + searchLimit)
    console.log("translate: " + translate);

    let responseEmbedding = NaN;
    let embedds = NaN;

    if (apiType === "AWS Serverless") {
      console.log("AWS serverless version")

      try {
        setResults([])
        responseEmbedding = await axios.post(`${apiUrl}/ai_embedding_get`, {
          text: search,
          model: "amazon.titan-embed-text-v1",
          translate: translate
        }, {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'x-api-key': `${apiKey}`,
          },
        });
        console.log(responseEmbedding.data.message);
        console.log(responseEmbedding.data);
        if (responseEmbedding.data.websites != null) {
          setData(responseEmbedding.data.websites);
        }
        embedds = responseEmbedding.data.embedds
        console.log("end of handleSearchSimilar");
        setIsLoading(false);
        setIsError(false);
      } catch (error) {
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
        setMessage(`There was an error on handleSearchSimilar. ${message}`);
      }

      try {
        const response = await axios.post(`${apiUrl}/website_similar`, {
          embedds: embedds,
          model: "amazon.titan-embed-text-v1",
          search: search,
          limit: searchLimit,
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
      } catch (error) {
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

    if (apiType === "Docker") {
      console.log("Docker version")
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
      } catch (error) {
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
