import React from "react";
import Input from "../Input/input";

const InputsForAllExceptLink = ({
  formik,
  handleSplitTextForEmbedding,
  handleCorrectUsingAI,
  handleTranslate,
  isLoading,
}) => {
  return (
    <>
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
      <div style={{ marginTop: "10px" }}>
        <button
          className={"button"}
          style={{ marginRight: "10px" }}
          onClick={() => handleSplitTextForEmbedding(formik.values)}
        >
          Split text for Embedding
        </button>
        <button
          className={"button"}
          style={{ marginRight: "10px" }}
          onClick={() => handleCorrectUsingAI(formik.values)}
        >
          Correct using AI
        </button>
        <button
          className={"button"}
          style={{ marginRight: "10px" }}
          onClick={() => handleTranslate(formik.values)}
        >
          Translate
        </button>
        <a
          className={"button"}
          style={{ marginRight: "10px" }}
          href="https://platform.openai.com/tokenizer"
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenAI Tokenizer
        </a>
      </div>
      {formik.values.text && (
        <div style={{ marginTop: "10px" }}>
          Length: {formik.values.text.length}
        </div>
      )}
      <br />
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
