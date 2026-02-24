import React from "react";
import { Link, NavLink } from "react-router-dom";
import { useFormik } from "formik";

import useSidebarToggle from "Common/UseSideberToggleHooks";
import { useNavigate, useParams } from "react-router-dom";

import { useManageLLM } from "../../../hooks/useManageLLM";
import SharedInputs from "../../../Common/sharedInputs";

import FormButtons from "../../../Common/FormButtons/formButtons"

const LenieLink = () => {
    const themeSidebarToggle = useSidebarToggle();

    const { id } = useParams();

    React.useEffect(() => {
        if (id) {
            handleGetLinkByID(id).then(() => null);
        }
    }, [id]);

    const formik = useFormik({
        initialValues: {
            id: "",
            author: "",
            source: "",
            language: "",
            url: "",
            tags: "",
            title: "",
            document_type: "link",
            summary: "",
            document_state_error: "",
            document_state: "",
            next_id: null,
            previous_id: null,
        },
        onSubmit: () => {},
    });

    const {
        message,
        isError,
        isLoading,
        handleGetPageByUrl,
        handleSaveWebsiteNext,
        handleSaveWebsiteToCorrect,
        handleGetLinkByID,
        handleGetEntryToReview,
    } = useManageLLM({
        formik,
    });

    return (
        <>
            <div
                className={`main-center-content-m-left main-center-content-m-left ${themeSidebarToggle ? "collapsed" : ""}`}>
                <div className="search__generator mt--50">
                    <h4 className="title color-white-title-home"> Link</h4>
                </div>

                <form onSubmit={formik.handleSubmit}>
                    <SharedInputs
                        formik={formik}
                        isLoading={isLoading}
                        handleGetLinkByID={handleGetLinkByID}
                        handleGetEntryToReview={handleGetEntryToReview}
                        handleGetPageByUrl={handleGetPageByUrl}
                    />
                    <br/>
                    <FormButtons
                        message={message}
                        formik={formik}
                        isError={isError}
                        isLoading={isLoading}
                        handleSaveWebsiteNext={handleSaveWebsiteNext}
                        handleSaveWebsiteToCorrect={handleSaveWebsiteToCorrect}
                    />
                </form>

                <div className="copyright-area-bottom">
                    <p><Link to="#">Reactheme©</Link> 2024. All Rights Reserved.</p>
                </div>
            </div>
        </>
    );
};

export default LenieLink;
