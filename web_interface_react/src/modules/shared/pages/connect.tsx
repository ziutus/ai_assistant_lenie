import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";
import { saveConnectionConfig } from "../services/storage";
import type { ApiType } from "../../../types";
import { DEFAULT_API_URLS } from "../../../types";

const Connect: React.FC = () => {
  const navigate = useNavigate();
  const { setApiKey, setApiUrl, setApiType, setDatabaseStatus } =
    React.useContext(AuthorizationContext);

  const [formApiType, setFormApiType] = useState<ApiType>("AWS Serverless");
  const [formApiUrl, setFormApiUrl] = useState(DEFAULT_API_URLS["AWS Serverless"]);
  const [formApiKey, setFormApiKey] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState("");

  const handleApiTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newType = e.target.value as ApiType;
    setFormApiType(newType);
    setFormApiUrl(DEFAULT_API_URLS[newType]);
  };

  const handleConnect = async () => {
    setError("");

    if (!formApiKey.trim()) {
      setError("API key is required");
      return;
    }

    setIsValidating(true);
    const headers = { "x-api-key": formApiKey };
    const timeout = 10000;

    // Step 1: Check infra API — validates key + returns DB status
    let dbStatus = "unknown";
    try {
      const response = await axios.get(`${formApiUrl}/infra/database/status`, {
        headers,
        timeout,
      });
      dbStatus = response.data;
    } catch (err: any) {
      setIsValidating(false);
      if (err.response?.status === 403 || err.response?.status === 401) {
        setError("Invalid API key. Check the key and try again.");
      } else if (err.code === "ECONNABORTED") {
        setError("Connection timed out. Check the API URL.");
      } else {
        setError(`Connection failed: ${err.message}`);
      }
      return;
    }

    // Step 2: If DB is up, also validate app API key
    if (dbStatus === "available") {
      try {
        await axios.get(`${formApiUrl}/website_list`, {
          params: { type: "link", limit: 1 },
          headers,
          timeout,
        });
      } catch (err: any) {
        setIsValidating(false);
        if (err.response?.status === 403 || err.response?.status === 401) {
          setError("Database is up, but App API rejected the key (403). Check your API key.");
        } else if (err.code === "ECONNABORTED") {
          setError("Database is up, but App API timed out.");
        } else {
          setError(`Database is up, but App API failed: ${err.message}`);
        }
        return;
      }
    }

    // All checks passed — save DB status and enter the app
    setIsValidating(false);
    setDatabaseStatus(dbStatus);
    applyAndRedirect();
  };

  const applyAndRedirect = () => {
    saveConnectionConfig({
      apiType: formApiType,
      apiUrl: formApiUrl,
      apiKey: formApiKey,
    });
    setApiType(formApiType);
    setApiUrl(formApiUrl);
    setApiKey(formApiKey);
    navigate("/list");
  };

  return (
    <div style={{ maxWidth: "500px", margin: "80px auto", padding: "20px" }}>
      <h2 style={{ marginBottom: "20px" }}>Connect to Lenie Backend</h2>

      <div style={{ marginBottom: "15px" }}>
        <label htmlFor="connect-api-key" style={{ display: "block", marginBottom: "4px", fontWeight: 500 }}>
          API Key
        </label>
        <input
          id="connect-api-key"
          type="password"
          value={formApiKey}
          onChange={(e) => setFormApiKey(e.target.value)}
          placeholder="Enter your API key"
          style={{ width: "100%", padding: "8px", fontSize: "14px" }}
        />
      </div>

      <div style={{ marginBottom: "15px" }}>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          disabled={isValidating}
          aria-expanded={showAdvanced}
          style={{
            background: "none",
            border: "none",
            color: "#007bff",
            cursor: "pointer",
            padding: 0,
            fontSize: "14px",
            textDecoration: "underline",
          }}
        >
          {showAdvanced ? "Hide advanced settings" : "Advanced settings"}
        </button>
        {!showAdvanced && (
          <div style={{ fontSize: "12px", color: "#6c757d", marginTop: "4px" }}>
            {formApiType} — {formApiUrl}
          </div>
        )}
      </div>

      {showAdvanced && (
        <>
          <div style={{ marginBottom: "15px" }}>
            <label htmlFor="connect-api-type" style={{ display: "block", marginBottom: "4px", fontWeight: 500 }}>
              API Type
            </label>
            <select
              id="connect-api-type"
              value={formApiType}
              onChange={handleApiTypeChange}
              style={{ width: "100%", padding: "8px", fontSize: "14px" }}
            >
              <option value="AWS Serverless">AWS Serverless</option>
              <option value="Docker">Docker</option>
            </select>
          </div>

          <div style={{ marginBottom: "15px" }}>
            <label htmlFor="connect-api-url" style={{ display: "block", marginBottom: "4px", fontWeight: 500 }}>
              API URL
            </label>
            <input
              id="connect-api-url"
              type="text"
              value={formApiUrl}
              onChange={(e) => setFormApiUrl(e.target.value)}
              style={{ width: "100%", padding: "8px", fontSize: "14px" }}
            />
          </div>
        </>
      )}

      {error && (
        <p className="errorText" style={{ marginBottom: "15px" }}>{error}</p>
      )}

      <button
        className="button"
        onClick={handleConnect}
        disabled={isValidating}
        style={{ width: "100%", padding: "10px", fontSize: "16px" }}
      >
        {isValidating ? "Connecting..." : "Connect"}
      </button>
      {isValidating && <div className="loader" style={{ marginTop: "10px" }}></div>}
    </div>
  );
};

export default Connect;
