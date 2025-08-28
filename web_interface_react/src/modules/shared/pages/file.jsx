import React, { useRef } from "react";
import useFileSubmit from "../hooks/useFileSubmit";

const UploadFile = () => {
  const { message, isLoading, isError, submitFile } = useFileSubmit();
  const fileInput = useRef(null);

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Upload File</h2>
      <input
        type="file"
        accept=".jpg"
        ref={fileInput}
        style={{ width: "400px" }}
      />

      <div
        className={"flexBox"}
        style={{ maxWidth: "400px", marginTop: "10px", marginBottom: "10px" }}
      >
        <div className="flex-grow"></div>

        {isLoading && <div className="loader"></div>}
        <button
          style={{ marginLeft: "5px" }}
          disabled={isLoading}
          className={"button"}
          onClick={() => submitFile(fileInput)}
        >
          Upload
        </button>
      </div>

      {isError && message && <div className="errorText">{message}</div>}
    </div>
  );
};

export default UploadFile;
