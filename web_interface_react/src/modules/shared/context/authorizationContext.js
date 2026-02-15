import React, { createContext } from "react";

export const AuthorizationContext = createContext({
  databaseStatus: "",
  setDatabaseStatus: () => {},
  vpnServerStatus: "",
  setVpnServerStatus: () => {},
  apiKey: "",
  setApiKey: () => {},
  apiUrl: "",
  setApiUrl: () => {},
  apiType: "",
  setApiType: () => {},
  sqsLength: -1,
  searchInDocument: "",
  searchType: "strict",
  setSqsLength: () => {},
  selectedDocumentType: "link",
  selectedDocumentState: "NEED_MANUAL_REVIEW",
  setSelectedDocumentType: () => {},
  setSelectedDocumentState: () => {},
  setSearchInDocument: () => {},
  setSearchType: () => {}
});

const AuthorizationProvider = ({ children }) => {

  const [databaseStatus, setDatabaseStatus] = React.useState("unknown");
  const [vpnServerStatus, setVpnServerStatus] = React.useState("unknown");
  const [sqsLength, setSqsLength] = React.useState(0);
  const [apiKey, setApiKey] = React.useState();
  const [apiType, setApiType] = React.useState("AWS Serverless");
  const [apiUrl, setApiUrl] = React.useState(
    "https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1",
  );
  const [selectedDocumentType, setSelectedDocumentType] = React.useState("link");
  const [selectedDocumentState, setSelectedDocumentState] = React.useState("NEED_MANUAL_REVIEW");
  const [searchInDocument, setSearchInDocument] = React.useState("");
  const [searchType, setSearchType] = React.useState("strict");

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
        searchInDocument,
        setSqsLength,
        selectedDocumentType,
        selectedDocumentState,
        setSelectedDocumentType,
        setSelectedDocumentState,
        setSearchInDocument,
        searchType,
        setSearchType,
      }}
    >
      {children}
    </AuthorizationContext.Provider>
  );
};

export default AuthorizationProvider;
