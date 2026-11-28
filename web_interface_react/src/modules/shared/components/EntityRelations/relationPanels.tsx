import React from "react";
import axios from "axios";
import ChapterModelPicker, { useChapterModel } from "../ChapterModelPicker/chapterModelPicker";
import EntityRelations from "./entityRelations";
import { type ApiProps, type Endpoint, errorText } from "./types";

type Result = { created: number; evidence_added: number; skipped_rejected: number; failed_calls?: number;
  usage?: { llm_cost_amount: string | number | null; llm_cost_currency: string | null };
  unresolved: { subject?: string; object?: string; quote?: string; qid?: string; labels?: string[] }[] };
function ResultSummary({ result }: { result: Result }) {
  return <div role="status">
    <p>Nowe: {result.created} · Nowe dowody: {result.evidence_added} · Pominięte odrzucone: {result.skipped_rejected}
      {result.failed_calls !== undefined && ` · Nieudane fragmenty: ${result.failed_calls}`}
      {result.usage && ` · Koszt: ${result.usage.llm_cost_amount === null ? "nieznany" : `${result.usage.llm_cost_amount} ${result.usage.llm_cost_currency ?? ""}`}`}</p>
    {result.unresolved.length > 0 && <><p>Nie dopasowano do rejestru — dodaj osobę/organizację i uruchom ponownie</p>
      <ul>{result.unresolved.map((item, i) => <li key={i}>{item.qid && /^Q\d+$/.test(item.qid)
        ? <a href={`https://www.wikidata.org/wiki/${item.qid}`} target="_blank" rel="noreferrer">{item.labels?.join(" / ") || item.qid} ({item.qid})</a>
        : <>{item.subject} — {item.object}{item.quote && <blockquote>{item.quote}</blockquote>}</>}</li>)}</ul></>}
  </div>;
}
export function DocumentRelations({ apiUrl, apiKey, documentId, onChange }: ApiProps & { documentId: number; onChange: () => void }) {
  const model = useChapterModel(apiUrl, apiKey, "/relation_extraction/model");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [result, setResult] = React.useState<Result | null>(null);
  const [revision, setRevision] = React.useState(0);
  return <details style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: 10, marginTop: 12 }}>
    <summary>Powiązania</summary>
    <ChapterModelPicker state={model} summary="Model powiązań" ariaLabel="Model do analizy powiązań" disabled={busy} />
    <button type="button" disabled={busy} onClick={async () => {
      setBusy(true); setError(""); setResult(null);
      try {
        const response = await axios.post(`${apiUrl}/document/${documentId}/relations/detect`, model.model ? { model: model.model } : {}, { headers: { "x-api-key": apiKey }, timeout: 0 });
        setResult(response.data); setRevision(n => n + 1); onChange();
      } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
    }}>Zbuduj powiązania</button>
    {busy && <p role="status">Budowanie powiązań… Operacja może potrwać kilka minut.</p>}
    {error && <p role="alert">{error}</p>}
    {result && <ResultSummary result={result} />}
    <EntityRelations apiUrl={apiUrl} apiKey={apiKey} path={`/document/${documentId}/relations`} revision={revision} onChange={onChange} />
  </details>;
}
export function RegistryRelations({ apiUrl, apiKey, entity, wikidataQid }: ApiProps & { entity: Endpoint; wikidataQid?: string | null }) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [result, setResult] = React.useState<Result | null>(null);
  const [revision, setRevision] = React.useState(0);
  return <details open style={{ marginTop: 12 }}><summary>Powiązania</summary>
    {entity.type === "person" && (wikidataQid ? <button type="button" disabled={busy} onClick={async () => {
      setBusy(true); setError(""); setResult(null);
      try {
        const response = await axios.post(`${apiUrl}/persons/${entity.id}/relations/wikidata`, undefined, { headers: { "x-api-key": apiKey }, timeout: 0 });
        setResult(response.data); setRevision(n => n + 1);
      } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
    }}>Pobierz z Wikidata</button> : <p>Uzupełnij identyfikator Wikidata osoby, aby pobrać powiązania.</p>)}
    {busy && <p role="status">Pobieranie z Wikidata…</p>}
    {error && <p role="alert">{error}</p>}
    {result && <ResultSummary result={result} />}
    <EntityRelations apiUrl={apiUrl} apiKey={apiKey} path={`/${entity.type === "person" ? "persons" : "organizations"}/${entity.id}/relations`} entity={entity} revision={revision} />
  </details>;
}
