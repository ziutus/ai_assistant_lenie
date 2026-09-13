import React from "react";
import Input from "../Input/input";
import ArticlePreparationPanel from "../ArticlePreparationPanel/articlePreparationPanel";
import MarkdownLineEditor from "../MarkdownLineEditor/markdownLineEditor";
import ArticleSourceComparison from "../ArticleSourceComparison/articleSourceComparison";
import EntitiesPanel from "../EntitiesPanel/entitiesPanel";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";
import type { ChunkForPreview } from "../../utils/chunkBoundaries";

// Mounted only in the webpage branch; its key resets the cache on document/run changes.
const WebpageLineEditor = ({ formik, disabled }: { formik: any; disabled: boolean }) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [chunks, setChunks] = React.useState<ChunkForPreview[] | null>(null);
  const value: string = formik.values.text_md || formik.values.text || "";
  const chunksTextSnapshot = React.useRef<string>(value);
  const runId = formik.values.analysis_run_id;
  const requestChunks = async () => {
    if (!runId) return;
    setChunks(null);
    const response = await axios.get<{ chunks: Array<Omit<ChunkForPreview, "original_text"> & { original_text?: string | null }> }>(
      `${apiUrl}/analysis_run/${runId}/chunks`, { headers: { "x-api-key": `${apiKey ?? ""}` } },
    );
    chunksTextSnapshot.current = value;
    setChunks(response.data.chunks.map(({ id, position, type, status, original_text }) => ({
      id, position, type, status, original_text: original_text ?? "",
    })));
  };
  const headers = { "x-api-key": `${apiKey ?? ""}` };
  const changeChunkType = async (id: number, type: string) => {
    await axios.patch(`${apiUrl}/chunk/${id}`, { type }, { headers });
  };
  const mergeChunk = async (id: number) => {
    await axios.post(`${apiUrl}/chunk/${id}/merge_with_next`, undefined, { headers });
  };
  const splitChunk = async (id: number, splitAtLines: number[]) => {
    await axios.post(`${apiUrl}/chunk/${id}/execute_split`, { split_at_lines: splitAtLines }, { headers });
  };
  return <MarkdownLineEditor formik={formik} disabled={disabled}
    chunks={runId ? chunks ?? undefined : undefined}
    chunksStale={value !== chunksTextSnapshot.current}
    onRequestChunks={runId && chunks === null ? requestChunks : undefined}
    onRefreshChunks={requestChunks}
    onChangeChunkType={runId ? changeChunkType : undefined}
    onMergeChunk={runId ? mergeChunk : undefined}
    onSplitChunk={runId ? splitChunk : undefined} />;
};

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
          <WebpageLineEditor key={`${formik.values.id}-${formik.values.analysis_run_id}`}
            formik={formik} disabled={isLoading} />
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
      {formik.values.document_type === "youtube" && (
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
      {formik.values.id && (
        <section style={{ marginTop: 16, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}>
          <strong>Etap 2: osoby, miejsca i organizacje</strong>
          <p style={{ margin: "5px 0 10px", color: "#475569" }}>
            Wykrywanie oraz weryfikacja encji działają w tle — możesz dalej edytować dokument.
          </p>
          <EntitiesPanel docId={formik.values.id} externalDisabled={isLoading} onBusyChange={onProcessingChange} />
        </section>
      )}
    </>
  );
};

export default InputsForAllExceptLink;
