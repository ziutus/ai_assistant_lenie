import React from "react";
import classes from "./authorization.module.css";
import Input from "../Input/input";
import { AuthorizationContext } from "../../context/authorizationContext";
import { useDatabase } from "../../hooks/useDatabase";
import { useVpnServer } from "../../hooks/useVpnServer";
import { useSqs } from "../../hooks/useSqs"

const Authorization = () => {
  const { databaseStatus, apiKey, apiUrl, infraApiUrl, apiType, setApiKey, setApiUrl, setInfraApiUrl, setApiType } =
    React.useContext(AuthorizationContext);
  const { handleDBStart, handleDBStatusGet, handleDBStop, isLoading } = useDatabase();
  const { handleVPNServerStart, handleVPNServerStop, handleVPNServerStatusGet, isLoadingVpnServer } = useVpnServer();

  const { vpnServerStatus } = React.useContext(AuthorizationContext);
  const { sqsLength} = React.useContext(AuthorizationContext);

  const { selectedDocumentType, selectedDocumentState, searchInDocument, searchType} = React.useContext(AuthorizationContext);



  const { fetchSqsSize } = useSqs()

  const generateClass = () => {
    switch (databaseStatus) {
      case "unknown":
        return classes.unknown;
      case "available":
        return classes.available;
      case "stopped":
        return classes.stopped;
      default:
        return {};
    }
  };

  const generateClassVpnServer = () => {
        switch (vpnServerStatus) {
            case "available":
                return "status-available"; // Klasa CSS dla dostępnego serwera
            case "stopped":
                return "status-stopped"; // Klasa CSS dla zatrzymanego serwera
            case "unknown":
            default:
                return "status-unknown"; // Klasa CSS dla serwera w nieznanym stanie
        }
    };

  return (
    <div className={classes.authorizationBox}>
      <h4>Authorization</h4>
      <form id={'database-form'} className={classes.grid}>

        <Input
          disabled={isLoading}
          value={apiType}
          label={'API Type'}
          onChange={(e) => {
            setApiType(e.target.value);
          }}
          id={'api-type'}
          name={'api-type'}
          type={'select'}
          className={classes.apiTypeSelect}
        >
          <option value="AWS Serverless">AWS Serverless</option>
          <option value="Docker">Docker</option>
        </Input>
        <Input
          disabled={isLoading}
          value={apiUrl}
          label={'Server API'}
          onChange={(e) => {
            setApiUrl(e.target.value);
          }}
          id={'server-api'}
          name={'server-api'}
          type={'text'}
        />
        {apiType === "AWS Serverless" && (
          <Input
            disabled={isLoading}
            value={infraApiUrl}
            label={'Infra API URL'}
            onChange={(e) => {
              setInfraApiUrl(e.target.value);
            }}
            id={'infra-api-url'}
            name={'infra-api-url'}
            type={'text'}
          />
        )}
        <Input
          disabled={isLoading}
          value={apiKey}
          label={'API key'}
          onChange={(e) => {
            setApiKey(e.target.value);
          }}
          id={'api-key'}
          name={'api-key'}
          type={'text'}
        />

        <div> SQS queue length: {sqsLength}
          <button disabled={isLoadingVpnServer} type={'button'} className={'button'} onClick={() => fetchSqsSize()}> Check size</button>
        </div>

        <div className={classes.dbStatus}>
          <p>
            DataBase status:{' '}
            <span className={generateClass()}>{databaseStatus}</span>
          </p>
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
            }}
          >
            {!!isLoading && <div className={'loader'}></div>}
            {databaseStatus === 'stopped' && (
              <button
                disabled={isLoading}
                type={'button'}
                className={'button'}
                onClick={() => handleDBStart()}
              >
                Start
              </button>
            )}
            {databaseStatus === 'available' && (
              <button
                disabled={isLoading}
                type={'button'}
                className={'button'}
                onClick={() => handleDBStop()}
              >
                Stop
              </button>
            )}
            <button
              disabled={isLoading}
              type={'button'}
              className={'button'}
              onClick={() => handleDBStatusGet()}
            >
              Check status
            </button>
          </div>
        </div>

        <div className={classes.vpnServerStatus}>
          <p>
            VPN Server status:{' '}
            <span className={generateClassVpnServer()}>{vpnServerStatus}</span>
          </p>
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
            }}
          >
            {!!isLoadingVpnServer && <div className={'loader'}></div>}
            {vpnServerStatus === 'stopped' && (
              <button disabled={isLoadingVpnServer} type={'button'} className={'button'} onClick={() => handleVPNServerStart()}> Start </button>
            )}
            {vpnServerStatus === 'running' && (
              <button disabled={isLoadingVpnServer} type={'button'} className={'button'} onClick={() => handleVPNServerStop()}> Stop </button>
            )}
            <button disabled={isLoadingVpnServer} type={'button'} className={'button'} onClick={() => handleVPNServerStatusGet()}> Check status</button>
          </div>
        </div>
      </form>
      <div>
        <span> Document type: { selectedDocumentType} </span>
        <span> Document status: {selectedDocumentState}</span>
        <span> Search in documents: {searchInDocument}</span>
        <span> Search type: {searchType}</span>
      </div>

    </div>
  );
};

export default Authorization;
