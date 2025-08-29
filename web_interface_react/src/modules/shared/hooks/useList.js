import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

export const useList = () => {
  const [data, setData] = React.useState(null);
  const [dataAllLength, setDataAllLength] = React.useState(0);
  const [message, setMessage] = React.useState(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const { selectedDocumentType, selectedDocumentState} = React.useContext(AuthorizationContext);

  React.useEffect(() => {
    handleGetList(selectedDocumentType, selectedDocumentState).then(() => null);  // Domyślne wartości na start
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleGetList = async (type, documentState, searchInDocument) => {
    setIsLoading(true);
    try {
      const response = await axios.get(`${apiUrl}/website_list`, {
        headers: {
          "x-api-key": `${apiKey}`,
        },
        params: { type, document_state: documentState, search_in_document: searchInDocument },
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
      setMessage(`There was an error on suggesting handleGetList. ${message}`);
    }
  };

  return { message, isLoading, isError, data, handleGetList, dataAllLength };
};
