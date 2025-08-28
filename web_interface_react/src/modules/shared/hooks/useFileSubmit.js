import axios from "axios";
import React from "react";

const useFileSubmit = () => {
  const [message, setMessage] = React.useState(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [isSuccess, setIsSuccess] = React.useState(false);

  const submitFile = async (fileInput) => {
    if (fileInput.current.files[0]) {
      const file = fileInput.current.files[0];
      const formData = new FormData();
      formData.append("file", file);
      try {
        await axios.post(
          "https://y448yz22yk.execute-api.us-east-1.amazonaws.com/v1/upload-file-simple",
          formData,
          {
            headers: {
              "Content-Type": "multipart/form-data",
            },
          },
        );
        setIsSuccess(true);
        setIsError(false);
        setIsLoading(false);
        setMessage("File uploaded successfully.");
        // alert("File uploaded successfully.");
      } catch (error) {
        setIsSuccess(false);
        setIsLoading(false);
        setIsError(true);
        setMessage(`Error while uploading file: ${error} `);
        // console.log("Error while uploading file: ", error);
      }
    } else {
      setIsSuccess(false);
      setIsLoading(false);
      setIsError(true);
      setMessage("Please select a file.");
      // alert("Please select a file.");
    }
  };
  return { submitFile, isError, isLoading, isSuccess, message };
};

export default useFileSubmit;
