import React from "react";
import classes from "./authorization.module.css";
import { AuthorizationContext } from "../../context/authorizationContext";
import { useDatabase } from "../../hooks/useDatabase";
import { useVpnServer } from "../../hooks/useVpnServer";
import { useSqs } from "../../hooks/useSqs";
import { clearConnectionConfig } from "../../services/storage";
import { useNavigate } from "react-router-dom";

const Authorization = () => {
  const { databaseStatus, apiType, apiUrl, setApiKey } =
    React.useContext(AuthorizationContext);
  const { handleDBStart, handleDBStatusGet, handleDBStop, isLoading } = useDatabase();
  const { handleVPNServerStart, handleVPNServerStop, handleVPNServerStatusGet, isLoading: isLoadingVpnServer } = useVpnServer();

  const { vpnServerStatus } = React.useContext(AuthorizationContext);
  const { sqsLength } = React.useContext(AuthorizationContext);
  const { selectedDocumentType, selectedDocumentState, searchInDocument, searchType } = React.useContext(AuthorizationContext);

  const { fetchSqsSize } = useSqs();
  const navigate = useNavigate();

  const generateClass = (): string => {
    switch (databaseStatus) {
      case "unknown":
        return classes.unknown;
      case "available":
        return classes.available;
      case "stopped":
        return classes.stopped;
      default:
        return "";
    }
  };

  const generateClassVpnServer = (): string => {
    switch (vpnServerStatus) {
      case "available":
        return "status-available";
      case "stopped":
        return "status-stopped";
      case "unknown":
      default:
        return "status-unknown";
    }
  };

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

      <form id={'database-form'} className={classes.grid}>
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
        <span> Document type: {selectedDocumentType} </span>
        <span> Document status: {selectedDocumentState}</span>
        <span> Search in documents: {searchInDocument}</span>
        <span> Search type: {searchType}</span>
      </div>
    </div>
  );
};

export default Authorization;
