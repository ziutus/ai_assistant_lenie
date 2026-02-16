import React from "react";
import Input from "../Input/input";

const InputsForAllExceptLink = ({
  formik,
  handleSplitTextForEmbedding,
  handleTranslate,
  handleRemoveNotNeededText,
  isLoading,
}) => {
  return (
    <>
      <Input
        disabled={isLoading}
        value={formik.values.text_md}
        label={"Website MarkDown content"}
        onChange={formik.handleChange}
        id={"text_md"}
        name={"text_md"}
        type={"text_md"}
        multiline
      />
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
            <button
                className={"button"}
                style={{marginRight: "10px"}}
                onClick={() => handleTranslate(formik.values)}
            >
                Translate
            </button>
            <button
                className={"button"}
                style={{marginRight: "10px"}}
                onClick={() => handleRemoveNotNeededText(formik.values)}
            >
                Clean Text
            </button>
            <a
                className={"button"}
                style={{marginRight: "10px"}}
                href="https://platform.openai.com/tokenizer"
                target="_blank"
                rel="noopener noreferrer"
            >
                OpenAI Tokenizer
            </a>
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
            value={formik.values.text_english}
            label={"English"}
            onChange={formik.handleChange}
            id={"text_english"}
            name={"text_english"}
            type={"text"}
            multiline
        />

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
    </>
  );
};

export default InputsForAllExceptLink;
