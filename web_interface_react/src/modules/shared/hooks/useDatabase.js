import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

export const useDatabase = () => {
  const [message, setMessage] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const { apiKey, apiUrl, infraApiUrl, apiType, setDatabaseStatus } =
    React.useContext(AuthorizationContext);
  const baseUrl = apiType === "AWS Serverless" ? infraApiUrl : apiUrl;

  const handleDBStatusGet = async () => {
    setDatabaseStatus("unknown");
    setIsLoading(true);
    try {
      const response = await axios.get(`${baseUrl}/infra/database/status`, {
        headers: {
          "Content-Type": "application/json",
          "x-api-key": `${apiKey}`,
        },
      });

      setMessage("");
      console.log(response.data);
      setDatabaseStatus(response.data);
      setIsLoading(false);
      setIsError(false);
    } catch (error) {
      console.log("Error found during checking DB status");
      console.error(error);
      let message = error.message;
      if (
        error.response &&
        error.response.status &&
        error.response.status === 403
      ) {
        message += " Check your API key first";
      }
      setIsLoading(false);
      setIsError(true);
      setMessage(`Error on handleGetLinkByID ${message}`);
    }
  };

  const handleDBStart = async () => {
    setIsLoading(true);
    try {
      const response = await axios.post(
        `${baseUrl}/infra/database/start`,
        {},
        {
          headers: {
            "Content-Type": "application/json",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      setMessage("");
      setIsError(false);
      console.log(response.data);
      await handleDBStatusGet();
    } catch (error) {
      console.log("Error found during starting DB");
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

  const handleDBStop = async () => {
    setIsLoading(true);
    try {
      const response = await axios.post(
        `${baseUrl}/infra/database/stop`,
        {},
        {
          headers: {
            "Content-Type": "application/json",
            "x-api-key": `${apiKey}`,
          },
        },
      );

      // setMessage("");
      console.log(response.data);
      await handleDBStatusGet();
    } catch (error) {
      console.log("Error found during stopping DB");
      console.error(error);
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
      setMessage(`Error on handleGetLinkByID ${message}`);
    }
  };

  return {
    handleDBStart,
    handleDBStop,
    handleDBStatusGet,
    isLoading,
    isError,
    message,
  };
};
