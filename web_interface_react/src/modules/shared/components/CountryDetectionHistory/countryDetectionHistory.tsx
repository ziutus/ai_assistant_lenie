import React from "react";
import axios from "axios";
import CollapsibleSection from "../CollapsibleSection/collapsibleSection";
import LlmPayloadView from "../LlmPayloadView/llmPayloadView";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";

type Decision = { country_slug: string; country_name: string; mention_count: number; decision: string; snippets: string[] | null };
export type CountryDetection = {
  id: number; created_at: string; trigger: string; text_source: string; text_chars: number; threshold: number;
  tags_added: string[]; decisions: Decision[]; llm_called: boolean; llm_model: string | null;
  llm_usage_log_id: number | null; llm_error: string | null; llm_prompt: string | null; llm_response: string | null;
};
const labels: Record<string, string> = {
  llm_confirmed: "LLM potwierdził", llm_rejected: "LLM odrzucił", llm_error: "Błąd LLM — nie oznaczono", abbreviation_confirmed: "Skrót potwierdzony",
};
interface Props { docId: number | string; apiUrl: string; apiKey: string | null | undefined; detectionId?: number }

// A changed document/connection starts with a fresh, collapsed disclosure.
export default function CountryDetectionHistory(props: Props) {
  return <History key={`${props.apiUrl}:${props.apiKey}:${props.docId}`} {...props} />;
}

function History({ docId, apiUrl, apiKey, detectionId }: Props) {
  const [activated, setActivated] = React.useState(false);
  const [rows, setRows] = React.useState<CountryDetection[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const [retry, setRetry] = React.useState(0);
  React.useEffect(() => {
    if (!activated) return;
    let active = true;
    const startedAt = Date.now();
    setLoading(true); setError(null);
    axios.get<{ detections: CountryDetection[] }>(`${apiUrl}/document/${docId}/country_detections?limit=5`, { headers: { "x-api-key": apiKey ?? "" } })
      .then(({ data }) => { if (active) setRows(data.detections); })
      .catch(err => {
        console.error("Country detection history", err);
        if (active) setError(describeRequestError(err, "Nie udało się pobrać historii wykrywania państw", { startedAt, context: { Dokument: docId } }));
      }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [activated, apiUrl, apiKey, docId, detectionId, retry]);

  return <CollapsibleSection title="Dlaczego te państwa? (historia wykrywania)" onToggle={e => { if (e.currentTarget.open) setActivated(true); }} style={{ marginTop: 8 }}>
    {loading && <p role="status">Ładowanie historii…</p>}
    {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /><button type="button" onClick={() => setRetry(n => n + 1)}>Spróbuj ponownie</button></div>}
    {activated && !loading && !error && rows.length === 0 && <p>Brak zapisanej historii wykrywania państw dla tego dokumentu.</p>}
    {!loading && !error && [...rows].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id).map(run => <article key={run.id} style={{ marginTop: 12, paddingLeft: 8, borderLeft: "3px solid #93c5fd" }}>
      <strong>{new Date(run.created_at).toLocaleString("pl-PL")}</strong>
      <p>{run.trigger === "detect_button" ? "Przycisk Wykryj państwa" : "Analiza chunków"} · {run.text_source === "document" ? "cały dokument" : "synteza analizy"} · {run.text_chars} znaków · Próg wzmianek: {run.threshold}</p>
      <p><strong>Dodane państwa:</strong> {run.tags_added.map(slug => run.decisions.find(d => d.country_slug === slug)?.country_name ?? slug).join(", ") || "nic nowego"}</p>
      <div style={{ overflowX: "auto" }}><table style={{ width: "100%", textAlign: "left" }}><thead><tr><th>Państwo</th><th>Wzmianki</th><th>Decyzja</th><th>Fragmenty</th></tr></thead><tbody>
        {[...run.decisions].sort((a, b) => b.mention_count - a.mention_count).map(d => <tr key={d.country_slug}>
          <td>{d.country_name}</td><td>{d.mention_count}</td><td>{d.decision === "auto_threshold" ? `Co najmniej ${run.threshold} wzmianek — bez LLM` : labels[d.decision] ?? d.decision}</td>
          <td>{d.snippets?.length ? <CollapsibleSection title={`Fragmenty (${d.snippets.length})`}>{d.snippets.map((s, i) => <blockquote key={i} style={{ whiteSpace: "pre-wrap" }}>{s}</blockquote>)}</CollapsibleSection> : "—"}</td>
        </tr>)}
      </tbody></table></div>
      {run.llm_called ? <div><strong>Wywołanie LLM</strong><p>Model: {run.llm_model ?? "—"} · Identyfikator wywołania: {run.llm_usage_log_id ?? "—"}</p>
        <LlmPayloadView countryDetection payload={{ request_text: run.llm_prompt, response_text: run.llm_response, error: run.llm_error }} />
      </div> : <p>LLM nie był pytany — wszystkie państwa przeszły próg wzmianek albo nie było kandydatów.</p>}
    </article>)}
  </CollapsibleSection>;
}
