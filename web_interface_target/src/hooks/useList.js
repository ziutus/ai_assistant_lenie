import axios from "axios";
import React from "react";
import { useSelector } from "react-redux";
import { RootState } from "Slices/theme/store";

export const useList = () => {
    const [data, setData] = React.useState(null);
    const [message, setMessage] = React.useState(null);
    const [isLoading, setIsLoading] = React.useState(false);
    const [isError, setIsError] = React.useState(false);

    const apiServer = useSelector((state) => state.api.apiServer);
    const apiKey = useSelector((state) => state.api.apiKey);

    React.useEffect(() => {
        handleGetList().then(() => null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);


    const handleGetList = async () => {
        setIsLoading(true);

        try {


            console.log("Asking API URL: " + apiServer);
            console.log("Using API KEY:" + apiKey);
            const response = await axios.get(`${apiServer}/website_list`, {
                headers: {
                    "x-api-key": `${apiKey}`,
                },
            });
            console.log(response.data.message);
            console.log(response.data);
            if (response.data.websites != null) {
                setData(response.data.websites);
            }
            console.log("end of handleGetList");
            setIsLoading(false);
            setIsError(false);
        } catch (error) {
            console.error("There was an error on handleGetList!", error);
            let message = error.message;
            if (
                error.response &&
                error.response.status &&
                error.response.status === 400
            ) {
                message += " Check your API key first";
            }
            setIsLoading(false);
            setIsError(true);
            setMessage(`There was an error on suggesting handleGetList. ${message}`);
        }
    };

    return { message, isLoading, isError, data, handleGetList };
};
