import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";
import ChapterModelPicker, { useChapterModel } from "../ChapterModelPicker/chapterModelPicker";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";
import { ROLE_LABEL, toneSpanStyle, STANCE_KEY, STANCE_OUTLIER, type ToneSpan } from "../../utils/toneSpans";

/** The document's stored tone passages (all chapters); failures just leave the list empty. */
export const useToneSpans = (apiUrl: string, apiKey: string | undefined, docId: string | undefined) => {
  const [spans, setSpans] = React.useState<ToneSpan[]>([]);
  React.useEffect(() => {
    setSpans([]);
    if (!docId) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${docId}/tone_spans`, { headers: { "x-api-key": apiKey ?? "" } });
        const data = await response.json();
        if (!cancelled && response.ok && data.status === "success") setSpans((data.spans ?? []) as ToneSpan[]);
      } catch {
        // passages are optional decoration — a failed fetch just leaves the text unmarked
      }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, apiKey, docId]);
  return [spans, setSpans] as const;
};

interface Props {
  docId?: string;
  currentChapter: number;
  /** The reader shows a short multi-heading article as one chapter: analyse and list every chapter then. */
  compact: boolean;
  spans: ToneSpan[];
  onSpansChange: (spans: ToneSpan[]) => void;
  /** Highlighting in the text; a host that does not highlight (`/ner`) omits both and the switch is not drawn. */
  highlight?: boolean;
  onHighlightChange?: (value: boolean) => void;
  /** Called after the chapter's tone changed (the tone without outliers was stored), so the tone panel reloads. */
  onToneChanged?: () => void;
}

const STATUS_LABEL: Record<ToneSpan["status"], string> = {
  proposed: "propozycja", confirmed: "potwierdzone", rejected: "odrzucone",
};

const SHORT_QUOTE = 220;

/** The backend explains its 409/502 refusals in Polish; show that sentence instead of a bare status. */
const failure = (err: unknown, operation: string, startedAt: number, context: Record<string, string | number>) => {
  const info = describeRequestError(err, operation, { startedAt, context });
  const message = (err as { response?: { data?: { message?: string } } })?.response?.data?.message;
  return message ? { ...info, summary: `${operation}: ${message}` } : info;
};

/**
 * "Wyróżnione fragmenty": on request, a model points to passages whose tone differs from the chapter (a malicious
 * remark, irony) and to the key sentence that states the substance, as verbatim quotes the reader highlights. A
 * reviewer confirms or rejects each one; "Ton bez fragmentów odstających" classifies the chapter again without the
 * outliers, so they do not set its overall tone. Nothing here runs by itself - not for books, not on import.
 */
const ToneSpansPanel: React.FC<Props> = ({
  docId, currentChapter, compact, spans, onSpansChange, highlight, onHighlightChange, onToneChanged,
}) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);
  const modelState = useChapterModel(apiUrl, apiKey);
  const [busy, setBusy] = React.useState<"detect" | "core" | null>(null);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);

  const scoped = React.useMemo(
    () => spans.filter((span) => compact || span.chapter_position === null || span.chapter_position === currentChapter),
    [spans, compact, currentChapter],
  );
  const live = scoped.filter((span) => span.status !== "rejected");
  const outliers = live.filter((span) => span.role === "outlier");
  const modelBody = modelState.model ? { model: modelState.model } : {};

  if (!docId) return null;

  const detect = async () => {
    if (busy) return;
    setBusy("detect");
    setError(null);
    setNote("");
    const startedAt = Date.now();
    try {
      const { data } = await axios.post(
        `${apiUrl}/document/${docId}/chapter/${currentChapter}/detect_tone_spans`,
        compact ? { ...modelBody, whole_document: true } : modelBody,
        { headers, timeout: 300000 },
      );
      const returned = (data.spans ?? []) as ToneSpan[];
      const others = spans.filter((span) => !compact
        && span.chapter_position !== null && span.chapter_position !== currentChapter);
      onSpansChange([...others, ...returned]);
      const found = returned.filter((span) => span.status !== "rejected").length;
      const parts = [`Model ${data.model}`, `${found} fragm.`];
      if (data.report?.fragments > 1) parts.push(`rozdział czytany w ${data.report.fragments} częściach`);
      if (data.report?.rejected_no_quote) parts.push(`odrzucono ${data.report.rejected_no_quote} z cytatem, którego nie ma w tekście`);
      if (data.report?.llm_cost_amount && data.report?.llm_cost_currency) {
        parts.push(`koszt ${Number(data.report.llm_cost_amount).toFixed(4)} ${data.report.llm_cost_currency}`);
      }
      setNote(`${parts.join(", ")}.`);
    } catch (err) {
      setError(failure(err, `Wykrywanie fragmentów (rozdział ${currentChapter})`, startedAt, { dokument: docId }));
    } finally {
      setBusy(null);
    }
  };

  const recomputeCore = async () => {
    if (busy) return;
    setBusy("core");
    setError(null);
    setNote("");
    const startedAt = Date.now();
    try {
      const { data } = await axios.post(
        `${apiUrl}/document/${docId}/chapter/${currentChapter}/core_tone`, modelBody, { headers, timeout: 300000 },
      );
      onToneChanged?.();
      setNote(`Ton bez fragmentów odstających: ${data.core_tone?.emotion ?? "?"} (model ${data.model}).`);
    } catch (err) {
      setError(failure(err, `Ton bez fragmentów odstających (rozdział ${currentChapter})`, startedAt, { dokument: docId }));
    } finally {
      setBusy(null);
    }
  };

  const review = async (span: ToneSpan, status: ToneSpan["status"]) => {
    setError(null);
    const startedAt = Date.now();
    try {
      const { data } = await axios.patch(`${apiUrl}/tone_spans/${span.id}`, { status }, { headers });
      onSpansChange(spans.map((item) => (item.id === span.id ? (data.span as ToneSpan) : item)));
    } catch (err) {
      setError(failure(err, "Zapis decyzji o fragmencie", startedAt, { fragment: span.id }));
    }
  };

  return (
    <details style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 10, marginTop: 12 }}>
      <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
        🔦 Wyróżnione fragmenty{live.length > 0 ? ` (${live.length})` : ""}
      </summary>
      <p style={{ fontSize: "0.8em", color: "#64748b", margin: "6px 0" }}>
        Na żądanie: model wskazuje fragmenty o odmiennym tonie (np. złośliwe) i zdania kluczowe. Nic nie uruchamia się samo.
      </p>
      {onHighlightChange && (
        <label style={{ fontSize: "0.82em", display: "block", margin: "4px 0" }}>
          <input type="checkbox" checked={highlight ?? true} onChange={(event) => onHighlightChange(event.target.checked)} />
          {" "}Podświetlaj w tekście
        </label>
      )}
      <ChapterModelPicker state={modelState} disabled={busy !== null} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <button type="button" disabled={busy !== null} onClick={() => void detect()}
          title="Model czyta cały rozdział (długi - we fragmentach). Wcześniejsze propozycje zostaną zastąpione, potwierdzone i odrzucone zostają.">
          {busy === "detect" ? "⏳ Szukam…" : "🔦 Wykryj fragmenty"}
        </button>
        {!compact && outliers.length > 0 && (
          <button type="button" disabled={busy !== null} onClick={() => void recomputeCore()}
            title="Ocenia ton rozdziału jeszcze raz, bez fragmentów odstających (bez odrzuconych)">
            {busy === "core" ? "⏳ Oceniam…" : "⚖️ Ton bez fragmentów odstających"}
          </button>
        )}
      </div>
      {note && <p role="status" style={{ color: "#166534", margin: "6px 0", fontSize: "0.82em" }}>{note}</p>}
      {error && (
        <div role="alert" style={{ color: "#a33" }}>
          <p>{error.summary}</p>
          <RequestErrorDetails details={error.details} />
        </div>
      )}
      {scoped.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
          {scoped.map((span) => {
            const style = toneSpanStyle(span.role === "key" ? STANCE_KEY : STANCE_OUTLIER);
            const quote = span.quote.length > SHORT_QUOTE ? `${span.quote.slice(0, SHORT_QUOTE)}…` : span.quote;
            return (
              <li key={span.id} style={{
                margin: "6px 0", padding: "6px 8px", borderRadius: 6, fontSize: "0.82em",
                borderLeft: `3px solid ${style?.tintBorder ?? "#94a3b8"}`, background: style?.tint ?? "#fff",
                opacity: span.status === "rejected" ? 0.55 : 1,
              }}>
                <strong>{style?.icon} {span.label}</strong>
                {" "}<small style={{ color: "#64748b" }}>
                  {ROLE_LABEL[span.role]}{span.importance ? ` · waga ${span.importance}/3` : ""} · {STATUS_LABEL[span.status]}
                </small>
                <div style={{ margin: "4px 0", textDecoration: span.status === "rejected" ? "line-through" : undefined }}>
                  „{quote}”
                </div>
                {span.note && <div style={{ color: "#475569" }}>{span.note}</div>}
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  {span.status !== "confirmed" && <button type="button" onClick={() => void review(span, "confirmed")}>✓ Potwierdź</button>}
                  {span.status !== "rejected" && <button type="button" onClick={() => void review(span, "rejected")}>✗ Odrzuć</button>}
                  {span.status !== "proposed" && <button type="button" onClick={() => void review(span, "proposed")}>↺ Cofnij</button>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </details>
  );
};

export default ToneSpansPanel;
