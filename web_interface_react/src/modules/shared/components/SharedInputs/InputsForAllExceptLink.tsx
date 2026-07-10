import React from "react";
import Input from "../Input/input";
import EntitiesPanel from "../EntitiesPanel/entitiesPanel";

interface InputsForAllExceptLinkProps {
  formik: any;
  handleSplitTextForEmbedding: (values: any) => void;
  handleRemoveNotNeededText: (values: any) => void;
  isLoading: boolean;
  // "Clean Text" applies portal cleanup rules (site_rules.json) — only makes
  // sense for webpage documents, so only the webpage editor passes true.
  showCleanText?: boolean;
}

const InputsForAllExceptLink = ({
  formik,
  handleSplitTextForEmbedding,
  handleRemoveNotNeededText,
  isLoading,
  showCleanText,
}: InputsForAllExceptLinkProps) => {
  return (
    <>
      {formik.values.text_md && (
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
      <Input
        disabled={isLoading}
        value={formik.values.text}
        label={"Website content"}
        onChange={formik.handleChange}
        id={"text"}
        name={"text"}
        type={"text"}
        multiline
      />{" "}
        <div style={{marginTop: "10px"}}>
            <button
                className={"button"}
                style={{marginRight: "10px"}}
                onClick={() => handleSplitTextForEmbedding(formik.values)}
            >
                Split text for Embedding
            </button>
            {showCleanText && (
                <button
                    className={"button"}
                    style={{marginRight: "10px"}}
                    onClick={() => handleRemoveNotNeededText(formik.values)}
                >
                    Clean Text
                </button>
            )}
        </div>
        {formik.values.text && (
            <div style={{marginTop: "10px"}}>
                Length: {formik.values.text.length}
                {" "}
                Word Count: {formik.values.text.trim().split(/\s+/).length}
                {" "}
                Embedding parts: {(formik.values.text.match(/\n{3}/g) || []).length + 1}
            </div>
        )}
        <br/>
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
      <EntitiesPanel docId={formik.values.id} />
    </>
  );
};

export default InputsForAllExceptLink;
