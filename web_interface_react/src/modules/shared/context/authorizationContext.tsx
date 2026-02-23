import React, { createContext, useEffect } from "react";
import type { ApiType, AuthorizationState } from "../../../types";
import { loadConnectionConfig, saveConnectionConfig } from "../services/storage";

export const AuthorizationContext = createContext<AuthorizationState>({
  databaseStatus: "",
  setDatabaseStatus: () => {},
  vpnServerStatus: "",
  setVpnServerStatus: () => {},
  apiKey: undefined,
  setApiKey: () => {},
  apiUrl: "",
  setApiUrl: () => {},
  apiType: "AWS Serverless",
  setApiType: () => {},
  sqsLength: -1,
  setSqsLength: () => {},
  searchInDocument: "",
  setSearchInDocument: () => {},
  searchType: "strict",
  setSearchType: () => {},
  selectedDocumentType: "link",
  setSelectedDocumentType: () => {},
  selectedDocumentState: "NEED_MANUAL_REVIEW",
  setSelectedDocumentState: () => {},
});

const AuthorizationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Lazy init from localStorage
  const saved = loadConnectionConfig();

  const [databaseStatus, setDatabaseStatus] = React.useState("unknown");
  const [vpnServerStatus, setVpnServerStatus] = React.useState("unknown");
  const [sqsLength, setSqsLength] = React.useState(0);
  const [apiKey, setApiKey] = React.useState<string | undefined>(saved.apiKey);
  const [apiType, setApiType] = React.useState<ApiType>(saved.apiType);
  const [apiUrl, setApiUrl] = React.useState(saved.apiUrl);
  const [selectedDocumentType, setSelectedDocumentType] = React.useState("link");
  const [selectedDocumentState, setSelectedDocumentState] = React.useState("NEED_MANUAL_REVIEW");
  const [searchInDocument, setSearchInDocument] = React.useState("");
  const [searchType, setSearchType] = React.useState("strict");

  // Sync connection config changes to localStorage
  useEffect(() => {
    if (apiKey) {
      saveConnectionConfig({
        apiType,
        apiUrl,
        apiKey,
      });
    }
  }, [apiType, apiUrl, apiKey]);

  return (
    <AuthorizationContext.Provider
      value={{
        databaseStatus,
        setDatabaseStatus,
        vpnServerStatus,
        setVpnServerStatus,
        apiKey,
        setApiKey,
        apiUrl,
        setApiUrl,
        apiType,
        setApiType,
        sqsLength,
        setSqsLength,
        searchInDocument,
        setSearchInDocument,
        selectedDocumentType,
        setSelectedDocumentType,
        selectedDocumentState,
        setSelectedDocumentState,
        searchType,
        setSearchType,
      }}
    >
      {children}
    </AuthorizationContext.Provider>
  );
};

export default AuthorizationProvider;
