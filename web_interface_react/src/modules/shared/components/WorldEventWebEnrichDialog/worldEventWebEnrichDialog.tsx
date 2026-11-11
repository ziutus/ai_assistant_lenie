import React from "react";
import { modelOptionText, isModelUnavailable } from "../../utils/modelDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import type { WorldEvent, Kind } from "../WorldEventCard/worldEventCard";
import { webEnrichApi, type Credits, type Estimate, type EnrichResult, type ModelConfig, type EnrichStep, type WikipediaResult } from "../WorldEventCard/webEnrichApi";

interface Props {
  event: WorldEvent; kinds: Kind[]; apiUrl: string; headers: Record<string, string>;
  onClose: () => void; onChanged: () => void;
}
const FIELDS = { description: "Opis", kind: "Rodzaj", event_date: "Data początku", event_date_end: "Data końca", is_ongoing: "Trwa nadal" };
type Field = keyof typeof FIELDS;
const money = (value: string | null | undefined) => value == null ? "koszt nieznany" : `$${Number(value).toLocaleString("pl-PL", { maximumFractionDigits: 6 })}`;

const WorldEventWebEnrichDialog = ({ event, kinds, apiUrl, headers, onClose, onChanged }: Props) => {
  const api = React.useMemo(() => webEnrichApi(apiUrl, headers), [apiUrl, headers]);
  const [config, setConfig] = React.useState<ModelConfig | null>(null);
  const [model, setModel] = React.useState("");
  const [step, setStep] = React.useState<EnrichStep>("wikipedia");
  const [wikipedia, setWikipedia] = React.useState<WikipediaResult | null>(null);
  const [withWikipedia, setWithWikipedia] = React.useState(false);
  const [pages, setPages] = React.useState(2);
  const [credits, setCredits] = React.useState<Credits | null>(null);
  const [estimate, setEstimate] = React.useState<Estimate | null>(null);
  const [result, setResult] = React.useState<EnrichResult | null>(null);
  const [checked, setChecked] = React.useState<Set<string>>(new Set());
  const [busy, setBusy] = React.useState(false);
  const [applied, setApplied] = React.useState(false);
  const [applyFailed, setApplyFailed] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const fail = React.useCallback((err: unknown, operation: string, startedAt: number) => {
    console.error(err);
    setError(describeRequestError(err, operation, { startedAt, context: { wydarzenie: event.id } }));
  }, [event.id]);
  const refreshCredits = React.useCallback(async () => {
    const started = Date.now();
    try { setCredits(await api.credits()); }
    catch (err) { setCredits(null); fail(err, "Nie udało się odczytać kredytów", started); }
  }, [api, fail]);
  React.useEffect(() => {
    let active = true;
    const started = Date.now();
    api.models().then((data) => { if (active) { setConfig(data); setModel(data.default_model ?? ""); } })
      .catch((err) => { if (active) fail(err, "Nie udało się pobrać modeli", started); });
    void refreshCredits();
    return () => { active = false; };
  }, [api, fail, refreshCredits]);
  React.useEffect(() => {
    let active = true;
    setEstimate(null);
    const started = Date.now();
    if (model) api.estimate(event.id, model, pages, step).then((data) => { if (active) setEstimate(data); })
      .catch((err) => { if (active) fail(err, "Nie udało się oszacować kosztu", started); });
    return () => { active = false; };
  }, [api, event.id, model, pages, step, fail]);
  React.useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onClose(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [busy, onClose]);
  const proposal = result?.proposal;
  const description = proposal?.description == null ? proposal?.description : proposal.description +
    (proposal.sources_used.length ? `\n\nŹródła:\n${[...new Set(proposal.sources_used.map((s) => s.url))].join("\n")}` : "");
  const value = (field: Field) => field === "description" ? description : proposal?.[field];
  const display = (field: Field, val: unknown) => field === "kind" ? kinds.find((k) => k.code === val)?.label ?? String(val) :
    typeof val === "boolean" ? (val ? "tak" : "nie") : val == null || val === "" ? "brak" : String(val);
  const participants = proposal ? [
    ...proposal.countries.map((ref) => ({ type: "country", ref, exists: event.participants.some((p) => p.country?.slug === ref) })),
    ...proposal.organizations.map((ref) => ({ type: "organization", ref, exists: event.participants.some((p) => p.organization?.name === ref) })),
  ] : [];
  const toggle = (key: string) => setChecked((old) => { const next = new Set(old); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const run = async () => {
    setBusy(true); setError(null); setResult(null); setChecked(new Set());
    const started = Date.now();
    try {
      const data = await api.enrich(event.id, model, pages, step, withWikipedia);
      setResult(data);
      if (step === "wikipedia") setWikipedia(data.wikipedia);
    }
    catch (err) { fail(err, "Nie udało się uzupełnić wydarzenia", started); }
    finally { await refreshCredits(); setBusy(false); }
  };
  const apply = async () => {
    setBusy(true); setError(null);
    const started = Date.now();
    try {
      const changes: Record<string, unknown> = { expected_version: event.version };
      for (const field of Object.keys(FIELDS) as Field[]) if (checked.has(field)) changes[field] = value(field);
      if (Object.keys(changes).length > 1) await api.patch(event.id, changes);
      for (const p of participants) if (checked.has(`${p.type}:${p.ref}`)) await api.participant(event.id, p.type, p.ref);
      setApplied(true); onChanged();
    } catch (err) {
      setApplyFailed(true);
      fail(err, "Nie udało się zastosować wszystkich zmian; część mogła zostać zapisana. Zamknij dialog i sprawdź odświeżone wydarzenie", started);
      onChanged();
    }
    finally { setBusy(false); }
  };
  const saveDefault = async () => {
    setBusy(true); setError(null);
    const started = Date.now();
    try { setConfig(await api.saveModel(model)); }
    catch (err) { fail(err, "Nie udało się zapisać domyślnego modelu", started); }
    finally { setBusy(false); }
  };
  return <div role="dialog" aria-modal="true" aria-label={`Uzupełnij z internetu: ${event.title}`}
    style={{ position: "fixed", left: "50%", top: 40, transform: "translateX(-50%)", zIndex: 1000, width: "min(760px, 92vw)", maxHeight: "85vh", overflowY: "auto", padding: 16, background: "white", border: "1px solid #94a3b8", borderRadius: 8, boxShadow: "0 6px 24px #0005" }}>
    <strong>🌐 {event.title}</strong>
    <p>Model proponuje zmiany. Zaznacz pola, które chcesz zastosować. Linki źródłowe zostaną dołączone do zaznaczonego opisu.</p>
    <label>Model <select aria-label="Model" value={model} disabled={busy || applied} onChange={(e) => setModel(e.target.value)}>
      {!model && <option value="">Brak dostępnego modelu</option>}
      {config?.models.map((m) => <option key={m.id} value={m.id} disabled={isModelUnavailable(m)}>{modelOptionText(m)}{m.id === config.default_model ? " — domyślny" : ""}</option>)}
    </select></label>{" "}
    <button disabled={!model || busy} onClick={saveDefault}>Ustaw jako domyślny</button>
    <p>{step === "wikipedia" ? "Wikipedia (bezpłatnie)" : "Internet (Serper + Firecrawl)"}</p>
    {step === "web" && <><p><label>Liczba stron do pobrania <select value={pages} disabled={busy || applied} onChange={(e) => setPages(Number(e.target.value))}>
      {[0, 1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}
    </select></label></p>
    {wikipedia?.found && <label><input type="checkbox" checked={withWikipedia} disabled={busy} onChange={(e) => setWithWikipedia(e.target.checked)} />Użyj artykułu z Wikipedii jako kontekstu</label>}</>}
    <p>Pozostało: Serper {credits?.serper.credits_left ?? "niedostępne"} · Firecrawl {credits?.firecrawl.remaining ?? "niedostępne"}</p>
    {estimate && <p>Szacunek: {step === "wikipedia" ? "Wikipedia: 0 kredytów" : `Serper: ${estimate.serper_credits} kredyt · Firecrawl: ${estimate.firecrawl_credits} kredytów`} · LLM ≈ {money(estimate.llm.est_cost_usd)}</p>}
    <button disabled={busy || !estimate || applied} onClick={run}>{step === "wikipedia" ? "Szukaj w Wikipedii" : "Szukaj w internecie"}</button>
    {wikipedia && step === "wikipedia" && <button disabled={busy || applied || applyFailed} onClick={() => { setEstimate(null); setStep("web"); }}>Szukaj dalej w internecie (Serper + Firecrawl)</button>}
    {wikipedia?.found && wikipedia.url && <p>Wikipedia: <a href={wikipedia.url} target="_blank" rel="noopener noreferrer">{wikipedia.lang}: {wikipedia.title}</a></p>}
    {wikipedia && !wikipedia.found && <p>Nie znaleziono artykułu w Wikipedii. Możesz poszukać dalej w internecie.</p>}
    {busy && <span role="status" className="spinner-border spinner-border-sm"> Trwa przetwarzanie…</span>}
    {error && <div role="alert">{error.summary}<RequestErrorDetails details={error.details} /></div>}
    {result && <>
      <p>Zużycie: Serper: {result.usage.serper_credits} kredyt · Firecrawl: {result.usage.firecrawl_credits} kredytów · LLM: {result.usage.llm.llm_cost_currency === "USD" ? money(result.usage.llm.llm_cost_amount) : `${result.usage.llm.llm_cost_amount ?? "koszt nieznany"} ${result.usage.llm.llm_cost_currency ?? ""}`}</p>
      <ul aria-label="Źródła">{result.sources.map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || s.url}</a><p>{s.snippet}</p></li>)}</ul>
      {Object.entries(result.rejected).map(([reason, count]) => <p key={reason}>Odrzucono ({reason}): {count}</p>)}
      {!proposal && (result.source_step === "web" || result.wikipedia.found) && <p>Model nie zwrócił poprawnej propozycji.</p>}
      {proposal?.sources_used.map((s, i) => <blockquote key={`${s.url}:${i}`}><q>{s.quote}</q> <a href={s.url} target="_blank" rel="noopener noreferrer">Źródło cytatu</a></blockquote>)}
      {proposal && <fieldset disabled={busy || applied || applyFailed}><legend>Proponowane zmiany</legend>
        {(Object.keys(FIELDS) as Field[]).filter((f) => f in proposal).map((f) => <label key={f} style={{ display: "block", whiteSpace: "pre-wrap", marginBottom: 8 }}>
          <input type="checkbox" checked={checked.has(f)} onChange={() => toggle(f)} />{FIELDS[f]}: {display(f, event[f])} → {display(f, value(f))}
        </label>)}
        {participants.map((p) => <label key={`${p.type}:${p.ref}`} style={{ display: "block" }}>
          <input type="checkbox" disabled={p.exists} checked={checked.has(`${p.type}:${p.ref}`)} onChange={() => toggle(`${p.type}:${p.ref}`)} />
          {p.type === "country" ? "Kraj" : "Organizacja"}: {p.exists ? "już uczestniczy" : "brak →"} {p.ref}
        </label>)}
        <button disabled={!checked.size} onClick={apply}>Zastosuj zaznaczone</button>
      </fieldset>}
    </>}
    {applied && <p role="status">Zastosowano zaznaczone zmiany.</p>}
    <button disabled={busy} onClick={onClose}>Zamknij</button>
  </div>;
};
export default WorldEventWebEnrichDialog;
