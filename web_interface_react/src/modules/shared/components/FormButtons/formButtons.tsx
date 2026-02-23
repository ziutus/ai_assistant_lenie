import React from "react";

interface FormButtonsProps {
  message: string;
  formik: any;
  isError: boolean;
  isLoading: boolean;
  handleSaveWebsiteNext: (values: any) => void;
  handleSaveWebsiteToCorrect: (values: any) => void;
  handleDeleteDocumentNext?: (values: any) => void;
}

const FormButtons = ({
  message,
  formik,
  isError,
  isLoading,
  handleSaveWebsiteNext,
  handleSaveWebsiteToCorrect,
  handleDeleteDocumentNext

}: FormButtonsProps) => {
  return (
    <>
      <button
        style={{ marginRight: "15px" }}
        className={"button"}
        onClick={() => handleSaveWebsiteToCorrect(formik.values)}
      >
        Zapisz do poprawy
      </button>
      <button
        style={{ marginRight: "15px" }}
        className={"button"}
        onClick={() => handleSaveWebsiteNext(formik.values)}
      >
        Zapisz i następny do poprawy
      </button>
      <button
        style={{ marginRight: "15px" }}
        className={"button"}
        onClick={() => handleDeleteDocumentNext?.(formik.values)}
      >
        Usuń
      </button>

      {isLoading && (
        <div className="loader" style={{ marginTop: "10px" }}></div>
      )}
      {message && isError && (
        <p className={isError ? "errorText" : ""} style={{ marginTop: "10px" }}>
          {message}
        </p>
      )}
    </>
  );
};

export default FormButtons;
