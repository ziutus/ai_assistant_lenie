import React from "react";
import Input from "../Input/input";
import EntitiesPanel from "../EntitiesPanel/entitiesPanel";
import ArticlePreparationPanel from "../ArticlePreparationPanel/articlePreparationPanel";
import MarkdownLineEditor from "../MarkdownLineEditor/markdownLineEditor";
import ArticleSourceComparison from "../ArticleSourceComparison/articleSourceComparison";

interface InputsForAllExceptLinkProps {
  formik: any;
  handleRemoveNotNeededText: (values: any) => void;
  isLoading: boolean;
  // "Clean Text" applies portal cleanup rules (site_rules.json) — only makes
  // sense for webpage documents, so only the webpage editor passes true.
  showCleanText?: boolean;
  onProcessingChange?: (busy: boolean) => void;
}

const InputsForAllExceptLink = ({
  formik,
  handleRemoveNotNeededText,
  isLoading,
  showCleanText,
  onProcessingChange,
}: InputsForAllExceptLinkProps) => {
  return (
    <>
      {showCleanText && <ArticlePreparationPanel formik={formik} />}
      {showCleanText ? (
        <div style={{
          display: "grid",
          gridTemplateColumns: "minmax(620px, 3fr) minmax(360px, 2fr)",
          gap: 14,
          alignItems: "start",
        }}>
          <MarkdownLineEditor formik={formik} disabled={isLoading} />
          <ArticleSourceComparison formik={formik} />
        </div>
      ) : formik.values.text_md && (
        <details style={{ marginBottom: "8px" }}>
          <summary style={{ cursor: "pointer" }}>Website MarkDown content</summary>
          <Input
            disabled={isLoading}
            value={formik.values.text_md}
            onChange={formik.handleChange}
            id={"text_md"}
            name={"text_md"}
            type={"text_md"}
            multiline
          />
        </details>
      )}
      {!showCleanText && (
        <Input disabled={isLoading} value={formik.values.text} label={"Website content"}
          onChange={formik.handleChange} id={"text"} name={"text"} type={"text"} multiline />
      )}{" "}
        {(showCleanText ? (formik.values.text_md || formik.values.text) : formik.values.text) && (
            <div style={{marginTop: "10px"}}>
                Długość: {(showCleanText ? (formik.values.text_md || formik.values.text) : formik.values.text).length} znaków
                {" · "}
                Słowa: {(showCleanText ? (formik.values.text_md || formik.values.text) : formik.values.text).trim().split(/\s+/).length}
                {formik.values.embeddings_count != null && (
                    <>
                        {" · "}
                        Embeddingi w bazie: {formik.values.embeddings_count}
                    </>
                )}
                {formik.values.approved_chunks_count != null && (
                    <>
                        {" · "}
                        Zatwierdzone chunki TEMAT: {formik.values.approved_chunks_count}
                    </>
                )}
            </div>
        )}
      <br/>
      {!showCleanText && (
        <Input
          disabled={isLoading}
          value={formik.values.chapter_list}
          label={"Chapter list:"}
          onChange={formik.handleChange}
          id={"chapter_list"}
          name={"chapter_list"}
          type={"text"}
          multiline
        />
      )}
      <Input
        disabled={isLoading}
        value={formik.values.note}
        label={"Note:"}
        onChange={formik.handleChange}
        id={"note"}
        name={"note"}
        type={"text"}
        multiline
      />
      <EntitiesPanel
        docId={formik.values.id}
        externalDisabled={isLoading}
        onBusyChange={onProcessingChange}
      />
    </>
  );
};

export default InputsForAllExceptLink;
