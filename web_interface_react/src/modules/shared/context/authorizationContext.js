import React, { createContext } from "react";
import { useEffect, useState } from 'react';

import { AwsRum } from 'aws-rum-web';



export const bootstrapRum = () => {
  if (window.location.hostname === 'localhost') {
    return;
  }

  // https://aws.amazon.com/blogs/mt/using-amazon-cloudwatch-rum-with-a-react-web-application-in-five-steps/
  try {
    const config = {
      sessionSampleRate: 1,
      identityPoolId: "us-east-1:69944c41-8591-41a0-9037-8fc91b005c17",
      endpoint: "https://dataplane.rum.us-east-1.amazonaws.com",
      telemetries: ["performance","errors","http"],
      allowCookies: true,
      enableXRay: true
    };

    const APPLICATION_ID = '88632d7f-4bb8-47e0-991b-76c7d20fd2ec';
    const APPLICATION_VERSION = '1.0.0';
    const APPLICATION_REGION = 'us-east-1';

    const awsRum2 = new AwsRum(
      APPLICATION_ID,
      APPLICATION_VERSION,
      APPLICATION_REGION,
      config
    );

    return awsRum2
  } catch (error) {
    // Ignore errors thrown during CloudWatch RUM web client initialization
  }
}

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
  awsRum: "",
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

  useEffect(() => {
    setAwsRum(bootstrapRum());
    console.log("I setup the AWSRum")

  }, []);

  const [awsRum, setAwsRum] = React.useState();
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
        awsRum,
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
