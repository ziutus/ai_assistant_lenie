import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";
import { DEFAULT_URLS, saveConnectionConfig } from "../services/storage";
import type { ApiType } from "../../../types";

const Connect: React.FC = () => {
  const navigate = useNavigate();
  const { setApiKey, setApiUrl, setInfraApiUrl, setApiType } =
    React.useContext(AuthorizationContext);

  const [formApiType, setFormApiType] = useState<ApiType>("AWS Serverless");
  const [formApiUrl, setFormApiUrl] = useState(DEFAULT_URLS["AWS Serverless"].apiUrl);
  const [formInfraApiUrl, setFormInfraApiUrl] = useState(DEFAULT_URLS["AWS Serverless"].infraApiUrl);
  const [formApiKey, setFormApiKey] = useState("");
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState("");
  const [skipValidation, setSkipValidation] = useState(false);

  const handleApiTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newType = e.target.value as ApiType;
    setFormApiType(newType);
    const defaults = DEFAULT_URLS[newType];
    setFormApiUrl(defaults.apiUrl);
    setFormInfraApiUrl(defaults.infraApiUrl);
  };

  const handleConnect = async () => {
    setError("");

    if (!formApiKey.trim()) {
      setError("API key is required");
      return;
    }

    if (skipValidation) {
      applyAndRedirect();
      return;
    }

    setIsValidating(true);
    try {
      await axios.get(`${formApiUrl}/website_list`, {
        params: { type: "link", limit: 1 },
        headers: { "x-api-key": formApiKey },
        timeout: 10000,
      });
      applyAndRedirect();
    } catch (err: any) {
      if (err.response?.status === 403 || err.response?.status === 401) {
        setError("Invalid API key. Check the key and try again.");
      } else if (err.code === "ECONNABORTED") {
        setError("Connection timed out. Check the server URL or skip validation.");
      } else {
        setError(`Connection failed: ${err.message}. You can skip validation if the backend is down.`);
      }
    } finally {
      setIsValidating(false);
    }
  };

  const applyAndRedirect = () => {
    saveConnectionConfig({
      apiType: formApiType,
      apiUrl: formApiUrl,
      infraApiUrl: formInfraApiUrl,
      apiKey: formApiKey,
    });
    setApiType(formApiType);
    setApiUrl(formApiUrl);
    setInfraApiUrl(formInfraApiUrl);
    setApiKey(formApiKey);
    navigate("/list");
  };

  return (
    <div style={{ maxWidth: "500px", margin: "80px auto", padding: "20px" }}>
      <h2 style={{ marginBottom: "20px" }}>Connect to Lenie Backend</h2>

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
          Server API URL
        </label>
        <input
          id="connect-api-url"
          type="text"
          value={formApiUrl}
          onChange={(e) => setFormApiUrl(e.target.value)}
          style={{ width: "100%", padding: "8px", fontSize: "14px" }}
        />
      </div>

      {formApiType === "AWS Serverless" && (
        <div style={{ marginBottom: "15px" }}>
          <label htmlFor="connect-infra-url" style={{ display: "block", marginBottom: "4px", fontWeight: 500 }}>
            Infra API URL
          </label>
          <input
            id="connect-infra-url"
            type="text"
            value={formInfraApiUrl}
            onChange={(e) => setFormInfraApiUrl(e.target.value)}
            style={{ width: "100%", padding: "8px", fontSize: "14px" }}
          />
        </div>
      )}

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
        <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={skipValidation}
            onChange={(e) => setSkipValidation(e.target.checked)}
          />
          Skip validation (use when backend is down)
        </label>
      </div>

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
