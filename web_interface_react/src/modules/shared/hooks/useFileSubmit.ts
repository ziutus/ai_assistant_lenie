import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

const useFileSubmit = () => {
  const [message, setMessage] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [isSuccess, setIsSuccess] = React.useState(false);
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);

  const submitFile = async (fileInput: React.RefObject<HTMLInputElement | null>): Promise<string | undefined> => {
    if (fileInput.current?.files?.[0]) {
      const file = fileInput.current.files[0];
      const formData = new FormData();
      formData.append("file", file);
      setIsLoading(true);
      setIsError(false);
      setIsSuccess(false);
      try {
        const response = await axios.post<{ key: string }>(
          `${apiUrl}/upload-file`,
          formData,
          {
            headers: {
              "Content-Type": "multipart/form-data",
              "x-api-key": apiKey ?? "",
            },
          },
        );
        setIsSuccess(true);
        setIsError(false);
        setIsLoading(false);
        setMessage(`Plik zapisany w MinIO: ${response.data.key}`);
        return response.data.key;
        // alert("File uploaded successfully.");
      } catch (error: any) {
        setIsSuccess(false);
        setIsLoading(false);
        setIsError(true);
        setMessage(`Error while uploading file: ${error} `);
        // console.log("Error while uploading file: ", error);
        return undefined;
      }
    } else {
      setIsSuccess(false);
      setIsLoading(false);
      setIsError(true);
      setMessage("Please select a file.");
      // alert("Please select a file.");
      return undefined;
    }
  };
  return { submitFile, isError, isLoading, isSuccess, message };
};

export default useFileSubmit;
