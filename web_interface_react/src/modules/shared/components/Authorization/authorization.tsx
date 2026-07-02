import React from "react";
import classes from "./authorization.module.css";
import { AuthorizationContext } from "../../context/authorizationContext";
import { clearConnectionConfig } from "../../services/storage";
import { useNavigate } from "react-router-dom";

const Authorization = () => {
  const { apiType, apiUrl, setApiKey } =
    React.useContext(AuthorizationContext);

  const { selectedDocumentType, selectedDocumentState, searchInDocument, searchType } = React.useContext(AuthorizationContext);

  const navigate = useNavigate();
  const [backendVersion, setBackendVersion] = React.useState<string | null>(null);

  // Fetch backend version on mount
  React.useEffect(() => {
    if (apiUrl) {
      fetch(`${apiUrl}/version`)
        .then(res => res.json())
        .then(data => {
          if (data.status === "success" && data.app_version) {
            setBackendVersion(data.app_version);
          }
        })
        .catch(() => setBackendVersion(null));
    }
  }, [apiUrl]);

  const handleDisconnect = () => {
    clearConnectionConfig();
    setApiKey(undefined);
    navigate("/connect");
  };

  return (
    <div className={classes.authorizationBox}>
      <h4>Backend Connection</h4>
      <div style={{ marginBottom: "10px", fontSize: "13px" }}>
        <span style={{ color: "#28a745", fontWeight: 500 }}>Connected</span>
        {" "}({apiType}) — {apiUrl}
        {backendVersion && <span style={{ marginLeft: "10px", color: "#6c757d" }}>Backend v{backendVersion}</span>}
        <button
          type="button"
          className="button"
          style={{ marginLeft: "10px", fontSize: "12px", padding: "2px 8px" }}
          onClick={() => navigate("/connect")}
        >
          Settings
        </button>
        <button
          type="button"
          className="button"
          style={{ marginLeft: "5px", fontSize: "12px", padding: "2px 8px" }}
          onClick={handleDisconnect}
        >
          Disconnect
        </button>
      </div>

      <div>
        <span> Document type: {selectedDocumentType} </span>
        <span> Document status: {selectedDocumentState}</span>
        <span> Search in documents: {searchInDocument}</span>
        <span> Search type: {searchType}</span>
      </div>
    </div>
  );
};

export default Authorization;
