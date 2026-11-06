import React from "react";
import axios from "axios";
import ChapterModelPicker, { useChapterModel } from "../ChapterModelPicker/chapterModelPicker";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";

/** What `POST /document/:id/chapter/:pos/detect_tone` and `.../detect_time_period` answer (the part the UI reads). */
export interface ChapterRunResponse<Item> {
  model: string;
  /** true = the model's answer was unusable and the stored result of the chapter was left alone. */
  kept_previous: boolean;
  items: Item[];
  report: {
    fragments?: number;
    fragments_skipped?: number;
    llm_cost_amount?: string | null;
    llm_cost_currency?: string | null;
    invalid_json?: number;
  };
}

interface Props<Item> {
  apiUrl: string;
  apiKey: string | undefined;
  docId: string | number;
  position: number;
  endpoint: "detect_tone" | "detect_time_period";
  /** Name of the list in the answer: `tones` or `time_periods`. */
  resultKey: "tones" | "time_periods";
  summary: string;
  buttonLabel: string;
  title: string;
  onResult: (result: ChapterRunResponse<Item>) => void;
}

export const describeRun = (result: ChapterRunResponse<unknown>, what: string): string => {
  const { report } = result;
  const parts = [`Model ${result.model}`];
  if (result.kept_previous) {
    parts.push(`odpowiedź była nieczytelna — ${what} bez zmian`);
  }
  if (report.fragments && report.fragments > 1) parts.push(`rozdział czytany w ${report.fragments} fragmentach`);
  if (report.fragments_skipped) parts.push(`pominięto ${report.fragments_skipped} fragm. (limit kosztów)`);
  if (report.llm_cost_amount && report.llm_cost_currency) {
    parts.push(`koszt ${Number(report.llm_cost_amount).toFixed(4)} ${report.llm_cost_currency}`);
  }
  return `${parts.join(", ")}.`;
};

/**
 * "Oceń rozdział": runs ONE per-chapter classification (tone or historical period) with a model chosen from the
 * allowed list (price and window shown), replacing the stored result of that chapter only. A chapter longer than one
 * model call is read in fragments (the backend merges them), it is not cut.
 */
function ChapterAnalysisRunner<Item>({
  apiUrl, apiKey, docId, position, endpoint, resultKey, summary, buttonLabel, title, onResult,
}: Props<Item>) {
  const modelState = useChapterModel(apiUrl, apiKey);
  const [busy, setBusy] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);

  const run = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote("");
    const startedAt = Date.now();
    try {
      const { data } = await axios.post(
        `${apiUrl}/document/${docId}/chapter/${position}/${endpoint}`,
        modelState.model ? { model: modelState.model } : {},
        { headers: { "x-api-key": apiKey ?? "" }, timeout: 300000 },
      );
      const result: ChapterRunResponse<Item> = {
        model: data.model, kept_previous: Boolean(data.kept_previous), items: data[resultKey] ?? [], report: data.report ?? {},
      };
      onResult(result);
      setNote(describeRun(result, resultKey === "tones" ? "poprzedni ton" : "poprzednie okresy"));
    } catch (err) {
      setError(describeRequestError(err, `${summary} (rozdział ${position})`, {
        startedAt, context: { dokument: docId, rozdział: position },
      }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 8 }}>
      <ChapterModelPicker state={modelState} disabled={busy} />
      <button type="button" disabled={busy} onClick={() => void run()} title={title}>
        {busy ? "⏳ Oceniam…" : buttonLabel}
      </button>
      {note && <p role="status" style={{ color: "#166534", margin: "4px 0", fontSize: "0.82em" }}>{note}</p>}
      {error && (
        <div role="alert" style={{ color: "#a33" }}>
          <p>{error.summary}</p>
          <RequestErrorDetails details={error.details} />
        </div>
      )}
    </div>
  );
}

export default ChapterAnalysisRunner;
