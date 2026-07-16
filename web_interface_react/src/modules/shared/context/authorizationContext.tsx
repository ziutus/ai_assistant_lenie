import React, { createContext, useEffect } from "react";
import type { ApiType, AuthorizationState } from "../../../types";
import { loadConnectionConfig, saveConnectionConfig, loadListFilters, saveListFilters } from "../services/storage";

export const AuthorizationContext = createContext<AuthorizationState>({
  apiKey: undefined,
  setApiKey: () => {},
  apiUrl: "",
  setApiUrl: () => {},
  apiType: "Docker",
  setApiType: () => {},
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
  const savedFilters = loadListFilters();

  const [apiKey, setApiKey] = React.useState<string | undefined>(saved.apiKey);
  const [apiType, setApiType] = React.useState<ApiType>(saved.apiType);
  const [apiUrl, setApiUrl] = React.useState(saved.apiUrl);
  const [selectedDocumentType, setSelectedDocumentType] = React.useState(savedFilters.documentType);
  const [selectedDocumentState, setSelectedDocumentState] = React.useState(savedFilters.documentState);
  const [searchInDocument, setSearchInDocument] = React.useState(savedFilters.searchText);
  const [searchType, setSearchType] = React.useState(savedFilters.searchType);

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

  // Persist list filters so a page reload doesn't reset the user's selections
  useEffect(() => {
    saveListFilters({
      documentType: selectedDocumentType,
      documentState: selectedDocumentState,
      searchText: searchInDocument,
      searchType,
    });
  }, [selectedDocumentType, selectedDocumentState, searchInDocument, searchType]);

  return (
    <AuthorizationContext.Provider
      value={{
        apiKey,
        setApiKey,
        apiUrl,
        setApiUrl,
        apiType,
        setApiType,
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
