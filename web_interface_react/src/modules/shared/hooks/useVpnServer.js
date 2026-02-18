import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

export const useVpnServer = () => {
    const [message, setMessage] = React.useState("");
    const [isLoading, setIsLoading] = React.useState(false);
    const [isError, setIsError] = React.useState(false);
    const { apiKey, apiUrl, infraApiUrl, apiType, setVpnServerStatus } = React.useContext(AuthorizationContext);
    const baseUrl = apiType === "AWS Serverless" ? infraApiUrl : apiUrl;

    const handleVPNServerStatusGet = async () => {
        setVpnServerStatus("unknown");
        setIsLoading(true);
        try {
            const response = await axios.get(`${baseUrl}/infra/vpn_server/status`, {
                headers: {
                    "Content-Type": "application/json",
                    "x-api-key": `${apiKey}`,
                },
            });

            setMessage("");
            console.log(response.data);
            setVpnServerStatus(response.data);
            setIsLoading(false);
            setIsError(false);
        } catch (error) {
            console.log("Error found during checking VPN server status");
            console.error(error);
            let message = error.message;
            if (error.response && error.response.status && error.response.status === 403) {
                message += " Check your API key first";
            }
            setIsLoading(false);
            setIsError(true);
            setMessage(`Error on handleVPNServerStatusGet ${message}`);
        }
    };

    const handleVPNServerStart = async () => {
        setIsLoading(true);
        try {
            const response = await axios.post(
                `${baseUrl}/infra/vpn_server/start`,
                {},
                {
                    headers: {
                        "Content-Type": "application/json",
                        "x-api-key": `${apiKey}`,
                    },
                },
            );

            setMessage("");
            setIsError(false);
            console.log(response.data);
            await handleVPNServerStatusGet();
        } catch (error) {
            console.log("Error found during starting VPN server");
            console.error(error);
            let message = error.message;
            if (error.response && error.response.status && error.response.status === 400) {
                message += " Check your API key first";
            }
            setMessage(`Error on handleVPNServerStart ${message}`);
            setIsLoading(false);
            setIsError(true);
        }
    };

    const handleVPNServerStop = async () => {
        setIsLoading(true);
        try {
            const response = await axios.post(
                `${baseUrl}/infra/vpn_server/stop`,
                {},
                {
                    headers: {
                        "Content-Type": "application/json",
                        "x-api-key": `${apiKey}`,
                    },
                },
            );

            console.log(response.data);
            await handleVPNServerStatusGet();
        } catch (error) {
            console.log("Error found during stopping VPN server");
            console.error(error);
            let message = error.message;
            if (error.response && error.response.status && error.response.status === 400) {
                message += " Check your API key first";
            }
            setIsLoading(false);
            setIsError(true);
            setMessage(`Error on handleVPNServerStop ${message}`);
        }
    };

    return {
        handleVPNServerStart,
        handleVPNServerStop,
        handleVPNServerStatusGet,
        isLoading,
        isError,
        message,
    };
};
