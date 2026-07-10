import React from "react";
import { NavLink } from "react-router-dom";
import Input from "../Input/input";
import EntitiesPanel from "../EntitiesPanel/entitiesPanel";

interface InputsForAllExceptLinkProps {
  formik: any;
  handleRemoveNotNeededText: (values: any) => void;
  isLoading: boolean;
  // "Clean Text" applies portal cleanup rules (site_rules.json) — only makes
  // sense for webpage documents, so only the webpage editor passes true.
  showCleanText?: boolean;
}

const InputsForAllExceptLink = ({
  formik,
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
            {formik.values.id && (
                <NavLink
                    className={"button"}
                    style={{marginRight: "10px"}}
                    to={`/chunks/${formik.values.id}`}
                >
                    Przegląd chunków →
                </NavLink>
            )}
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
                Długość: {formik.values.text.length} znaków
                {" · "}
                Słowa: {formik.values.text.trim().split(/\s+/).length}
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
