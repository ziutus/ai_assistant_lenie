import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

export const useSqs = () => {
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const { apiKey, apiUrl, infraApiUrl, apiType, setSqsLength } = React.useContext(AuthorizationContext);
  const baseUrl = apiType === "AWS Serverless" ? infraApiUrl : apiUrl;

  const fetchSqsSize = async () => {
    setIsLoading(true);
    try {
      const response = await axios.get(`${baseUrl}/infra/sqs/size`, {
        headers: {
          "Content-Type": "application/json",
          "x-api-key": `${apiKey}`,
        },
      });
      console.log("number of elements in SQS queue:" + response.data)
      setSqsLength(response.data);
      setIsLoading(false);
      setIsError(false);
    } catch (error) {
      console.log("Error found during fetching SQS size");
      console.error(error);
      setIsLoading(false);
      setIsError(true);
      setSqsLength(-1)
    }
  };

  return {
    fetchSqsSize,
    isLoading,
    isError,
  };
};
