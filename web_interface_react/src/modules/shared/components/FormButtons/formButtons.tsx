import React from "react";

interface FormButtonsProps {
  message: string;
  formik: any;
  isError: boolean;
  isLoading: boolean;
  // `destination` is only used for YouTube documents: "ner" or "chunks".
  handleSaveWebsiteNext: (values: any, destination?: "ner" | "chunks") => void;
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
        type="button"
        disabled={isLoading}
        style={{ marginRight: "15px" }}
        className={"button"}
        onClick={() => handleSaveWebsiteToCorrect(formik.values)}
      >
        Zapisz
      </button>
      <button
        type="button"
        disabled={isLoading || (formik.values.document_type === "youtube" && !String(formik.values.text || "").trim())}
        style={{ marginRight: "15px" }}
        className={"button"}
        onClick={() => handleSaveWebsiteNext(formik.values, "ner")}
      >
        {formik.values.document_type === "webpage"
          ? "Zatwierdź Markdown i przejdź do chunków"
          : formik.values.document_type === "youtube"
            ? "Zapisz i przejdź do przeglądu NER"
            : "Zapisz jako gotowy i przejdź dalej"}
      </button>
      {formik.values.document_type === "youtube" && (
        <button
          type="button"
          disabled={isLoading || !String(formik.values.text || "").trim()}
          style={{ marginRight: "15px" }}
          className={"button"}
          title="Zapisuje tak samo, ale pomija przegląd NER per rozdział"
          onClick={() => handleSaveWebsiteNext(formik.values, "chunks")}
        >
          Przejdź prosto do chunków
        </button>
      )}
      <button
        type="button"
        disabled={isLoading}
        style={{ marginRight: "15px" }}
        className={"button"}
        onClick={() => handleDeleteDocumentNext?.(formik.values)}
      >
        Usuń
      </button>

      {isLoading && (
        <div className="loader" style={{ marginTop: "10px" }}></div>
      )}
      {message && (
        <p className={isError ? "errorText" : ""} style={{ marginTop: "10px" }}>
          {message}
        </p>
      )}
    </>
  );
};

export default FormButtons;
