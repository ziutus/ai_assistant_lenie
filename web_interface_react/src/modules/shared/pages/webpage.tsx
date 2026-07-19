import React from "react";
import { useFormik } from "formik";
import { useManageLLM } from "../hooks/useManageLLM";
import SharedInputs from "../components/SharedInputs/sharedInputs";
import InputsForAllExceptLink from "../components/SharedInputs/InputsForAllExceptLink";
import { useParams, NavLink } from "react-router-dom";
import FormButtons from "../components/FormButtons/formButtons";
import { AuthorizationContext } from '../context/authorizationContext';

const Webpage = () => {
  const { id } = useParams();
  const { selectedDocumentType, selectedDocumentState} = React.useContext(AuthorizationContext);

  React.useEffect(() => {
    if (id) {
      handleGetLinkByID(id).then(() => null);
    }
  }, [id]);

  const formik: any = useFormik({
    initialValues: {
      id: "",
      byline: "",
      source: "",
      language: "",
      url: "",
      tags: "",
      title: "",
      document_type: "webpage",
      summary: "",
      text: "",
      text_md: "",
      document_state: "",
      document_state_error: "",
      chapter_list: "",
      note: "",
      next_id: null,
      previous_id: null,
      next_type: "",
      previous_type: "",
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
    handleRemoveNotNeededText
  } = useManageLLM({
    formik, selectedDocumentType, selectedDocumentState
  });

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: "10px" }}>
        <h2 style={{ margin: 0 }}>Webpage</h2>
        {id && (
          <NavLink
            className={"button"}
            to={`/chunks/${id}`}
            state={{ docType: "webpage" }}
            style={{ fontSize: "0.85em" }}
          >
            Analiza chunków
          </NavLink>
        )}
      </div>
      <form onSubmit={formik.handleSubmit} style={{ maxWidth: "800px" }}>
        <SharedInputs
          formik={formik}
          isLoading={isLoading}
          handleGetLinkByID={(id: any) => handleGetLinkByID(id, true)}
          handleGetEntryToReview={handleGetEntryToReview}
          handleGetPageByUrl={handleGetPageByUrl}
        />
        <InputsForAllExceptLink
          formik={formik}
          isLoading={isLoading}
          handleRemoveNotNeededText={handleRemoveNotNeededText}
          showCleanText
        />

        <FormButtons
          message={message}
          formik={formik}
          isError={isError}
          isLoading={isLoading}
          handleSaveWebsiteNext={handleSaveWebsiteNext}
          handleSaveWebsiteToCorrect={handleSaveWebsiteToCorrect}
        />
      </form>
    </div>
  );
};

export default Webpage;
