import React from "react";
import { useFormik } from "formik";
import { useManageLLM } from "../hooks/useManageLLM";
import SharedInputs from "../components/SharedInputs/sharedInputs";
import InputsForAllExceptLink from "../components/SharedInputs/InputsForAllExceptLink";
import { useParams } from "react-router-dom";
import FormButtons from "../components/FormButtons/formButtons";
import { AuthorizationContext } from '../context/authorizationContext';


const Youtube = () => {
  const { id } = useParams();
  const { selectedDocumentType, selectedDocumentState} = React.useContext(AuthorizationContext);

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
      document_type: "youtube",
      summary: "",
      text: "",
      text_english: "",
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
    handleSplitTextForEmbedding,
    handleRemoveNotNeededText,
  } = useManageLLM({
    formik, selectedDocumentType, selectedDocumentState
  });

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Youtube</h2>
      <form onSubmit={formik.handleSubmit} style={{ maxWidth: "800px" }}>
        <SharedInputs
          formik={formik}
          isLoading={isLoading}
          handleGetLinkByID={(id) => handleGetLinkByID(id, true)}
          handleGetEntryToReview={handleGetEntryToReview}
          handleGetPageByUrl={handleGetPageByUrl}
        />
        <InputsForAllExceptLink
          formik={formik}
          handleSplitTextForEmbedding={handleSplitTextForEmbedding}
          isLoading={isLoading}
          handleRemoveNotNeededText={handleRemoveNotNeededText}
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

export default Youtube;
