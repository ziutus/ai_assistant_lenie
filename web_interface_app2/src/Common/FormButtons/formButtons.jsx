import React from "react";

const FormButtons = ({
  message,
  formik,
  isError,
  isLoading,
  handleSaveWebsiteNext,
  handleSaveWebsiteToCorrect,
}) => {
  return (
    <>
      <button
        style={{ marginRight: "15px" }}
        className="rts-btn btn-primary w-25"
        onClick={() => handleSaveWebsiteToCorrect(formik.values)}
      >
        Zapisz do poprawy
      </button>
      <button
          className="rts-btn btn-primary w-50"
        onClick={() => handleSaveWebsiteNext(formik.values)}
      >
        Zapisz i nastepny do poprawy
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
