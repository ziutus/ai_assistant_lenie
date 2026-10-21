import React from "react";
import axios from "axios";
import { modelOptionText, type ModelOption } from "../../utils/modelDetails";

interface Candidate { key: string; kind: "organization" | "person"; name: string; mentions: number }
interface Proposal extends Candidate {
  entity_id: number | null;
  registry_id: number;
  status: "ok" | "insufficient_context" | "error";
  description: string | null;
  error_code: string | null;
}
interface Usage { tokens: number | null; cost: string | null; currency: string | null }

interface Props {
  apiUrl: string;
  apiKey: string;
  docId: string | number;
  position: number;
  /** Called after at least one description was saved, so the host can refresh its entity chips. */
  onSaved?: () => void;
}

const KIND_LABELS = { organization: "🏢 organizacja", person: "👤 osoba" } as const;

/**
 * "Uzupełnij brakujące opisy": the organizations and persons of ONE chapter that have no description are
 * described together — one prompt, one quotation of the chapter, one JSON answer
 * (`POST /document/:id/chapter/:pos/describe_entities`). The model only proposes; the reviewer edits and
 * approves, and only "Zapisz zaznaczone" writes (`PATCH /organizations/:id`, `PATCH /persons/:id`).
 */
const ChapterDescriptionsPanel = ({ apiUrl, apiKey, docId, position, onSaved }: Props) => {
  const headers = React.useMemo(() => ({ "Content-Type": "application/json", "x-api-key": apiKey }), [apiKey]);
  const url = `${apiUrl}/document/${docId}/chapter/${position}/describe_entities`;
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [candidates, setCandidates] = React.useState<Candidate[] | null>(null);
  const [models, setModels] = React.useState<ModelOption[]>([]);
  const [model, setModel] = React.useState("");
  const [proposals, setProposals] = React.useState<Proposal[]>([]);
  const [texts, setTexts] = React.useState<Record<string, string>>({});
  const [checked, setChecked] = React.useState<Set<string>>(new Set());
  const [usage, setUsage] = React.useState<Usage | null>(null);

  const reset = () => {
    setCandidates(null); setProposals([]); setTexts({}); setChecked(new Set()); setUsage(null); setMessage("");
  };
  const errorText = (error: unknown) =>
    (axios.isAxiosError(error) ? error.response?.data?.message : "") || (error as Error).message || "błąd";

  const start = async () => {
    setOpen(true);
    reset();
    setBusy(true);
    try {
      const { data } = await axios.post(url, { dry_run: true }, { headers });
      setCandidates(data.candidates ?? []);
      setModels(data.models ?? []);
      setModel(data.default_model ?? data.models?.[0]?.id ?? "");
      if ((data.candidates ?? []).length === 0) {
        setMessage("Organizacje i osoby tego rozdziału mają już opisy (albo nie są powiązane z rejestrem).");
      }
    } catch (error) {
      setMessage(`Nie udało się sprawdzić rozdziału: ${errorText(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true);
    setMessage("");
    try {
      const { data } = await axios.post(url, { model }, { headers, timeout: 180000 });
      const found: Proposal[] = data.proposals ?? [];
      setProposals(found);
      setTexts(Object.fromEntries(found.map((proposal) => [proposal.key, proposal.description ?? ""])));
      setChecked(new Set(found.filter((proposal) => proposal.status === "ok").map((proposal) => proposal.key)));
      setUsage(data.usage ?? null);
      if (!found.some((proposal) => proposal.status === "ok")) {
        setMessage("Model nie znalazł w rozdziale podstaw do żadnego opisu.");
      }
    } catch (error) {
      setMessage(`Model nie odpowiedział: ${errorText(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    const selected = proposals.filter((proposal) => checked.has(proposal.key) && (texts[proposal.key] ?? "").trim());
    if (selected.length === 0) return;
    setBusy(true);
    setMessage("");
    const saved = new Set<string>();
    let failure = "";
    for (const proposal of selected) {
      const endpoint = proposal.kind === "organization" ? "organizations" : "persons";
      try {
        await axios.patch(`${apiUrl}/${endpoint}/${proposal.registry_id}`,
          { description: texts[proposal.key].trim() }, { headers });
        saved.add(proposal.key);
      } catch (error) {
        failure = `Nie udało się zapisać „${proposal.name}”: ${errorText(error)}`;
        break;
      }
    }
    setProposals((current) => current.filter((proposal) => !saved.has(proposal.key)));
    setChecked((current) => new Set([...current].filter((key) => !saved.has(key))));
    setMessage(failure || `Zapisano ${saved.size} ${saved.size === 1 ? "opis" : "opisy"}.`);
    setBusy(false);
    if (saved.size > 0) onSaved?.();
  };

  const toggle = (key: string) => setChecked((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  if (!open) {
    return (
      <button type="button" onClick={() => void start()} style={{ marginTop: 6 }}
        title="Opisze jednym zapytaniem do modelu wszystkie organizacje i osoby tego rozdziału, które nie mają opisu">
        🤖 Uzupełnij brakujące opisy
      </button>
    );
  }
  const waitingForModel = candidates !== null && candidates.length > 0 && proposals.length === 0;
  return (
    <div aria-label="Brakujące opisy rozdziału" style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
      <div>
        <strong>Brakujące opisy</strong>
        <button type="button" style={{ marginLeft: 8 }} onClick={() => { setOpen(false); reset(); }}>✕ zamknij</button>
      </div>
      {busy && !candidates && <p>Sprawdzam rozdział…</p>}
      {waitingForModel && (
        <div>
          <p style={{ margin: "6px 0" }}>
            Bez opisu ({candidates?.length}):{" "}
            {candidates?.map((candidate) => `${candidate.name} (${KIND_LABELS[candidate.kind].split(" ")[0]})`).join(", ")}.
            Rozdział zostanie zacytowany raz, a model opisze wszystkie pozycje jednym zapytaniem.
          </p>
          <label>Model{" "}
            <select value={model} onChange={(event) => setModel(event.target.value)}>
              {models.map((option) => <option key={option.id} value={option.id}>{modelOptionText(option)}</option>)}
            </select>
          </label>
          {models.find((option) => option.id === model)?.supports_structured_outputs === false && (
            <p role="note" style={{ margin: "6px 0 0", color: "#475569" }}>
              Ten model nie wymusza formatu JSON — odpowiedź jest odczytywana z tekstu i częściej wymaga ponowienia.
            </p>
          )}
          {models.find((option) => option.id === model)?.external && (
            <p role="note" style={{ margin: "6px 0 0", color: "#92400e" }}>
              ⚠ Ten model wysyła tekst rozdziału do zewnętrznego pośrednika (OpenRouter).
            </p>
          )}
          <div>
            <button className={"button"} type="button" style={{ marginTop: 6 }} disabled={busy || !model}
              onClick={() => void generate()}>
              {busy ? "Pracuję…" : "Generuj opisy"}
            </button>
          </div>
        </div>
      )}
      {proposals.length > 0 && (
        <div>
          {proposals.map((proposal) => (
            <div key={proposal.key} style={{ padding: "6px 0", borderTop: "1px solid #dbe4f0" }}>
              <label>
                <input type="checkbox" disabled={proposal.status !== "ok"} checked={checked.has(proposal.key)}
                  onChange={() => toggle(proposal.key)} />{" "}
                <strong>{proposal.name}</strong>{" "}
                <span style={{ color: "#64748b", fontSize: "0.85em" }}>{KIND_LABELS[proposal.kind]} · ×{proposal.mentions}</span>
              </label>
              {proposal.status === "ok" && (
                <textarea aria-label={`Opis: ${proposal.name}`} rows={2} value={texts[proposal.key] ?? ""}
                  onChange={(event) => setTexts((current) => ({ ...current, [proposal.key]: event.target.value }))}
                  style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 2 }} />
              )}
              {proposal.status === "insufficient_context" && (
                <div style={{ color: "#64748b", fontSize: "0.9em" }}>Rozdział nie wystarcza do opisu.</div>
              )}
              {proposal.status === "error" && (
                <div style={{ color: "#a33", fontSize: "0.9em" }}>Model nie odpowiedział: {proposal.error_code ?? "błąd"}.</div>
              )}
            </div>
          ))}
          <button className={"button"} type="button" style={{ marginTop: 6 }}
            disabled={busy || ![...checked].some((key) => (texts[key] ?? "").trim())} onClick={() => void save()}>
            {busy ? "Zapisuję…" : "Zapisz zaznaczone"}
          </button>
          {usage && usage.tokens != null && (
            <span style={{ marginLeft: 8, color: "#64748b", fontSize: "0.85em" }}>
              {usage.tokens} tok.{usage.cost != null ? ` · ${usage.cost} ${usage.currency ?? ""}` : " · koszt nieznany"}
            </span>
          )}
        </div>
      )}
      {message && <p role="status" style={{ margin: "6px 0 0" }}>{message}</p>}
    </div>
  );
};

export default ChapterDescriptionsPanel;
