import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

type CostRow = { currency: string | null; calls: number; tokens: number; cost: string | null; unknown_calls?: number };
type OperationRow = CostRow & { operation: string; model: string };
type DailyRow = CostRow & { day: string };
type AnalysisRow = CostRow & { job_id: string; run_id: number | null; started_at: string | null };
type DocumentRow = CostRow & { document_id: number | null; title: string | null };
type Report = { totals: CostRow[]; documents: DocumentRow[]; daily: DailyRow[]; operations: OperationRow[]; analyses: AnalysisRow[] };

const iso = (d: Date) => d.toISOString().slice(0, 10);
const money = (value: string | null, currency: string | null) => value == null ? "—" : `${Number(value).toFixed(6)} ${currency ?? "?"}`;

const LlmCosts = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [params, setParams] = useSearchParams();
  const now = new Date();
  const [from, setFrom] = React.useState(params.get("from") ?? iso(new Date(now.getFullYear(), now.getMonth(), 1)));
  const [to, setTo] = React.useState(params.get("to") ?? iso(now));
  const [documentId, setDocumentId] = React.useState(params.get("document_id") ?? "");
  const [report, setReport] = React.useState<Report | null>(null);
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true); setError("");
    try {
      const query: Record<string, string> = { from, to };
      if (documentId.trim()) query.document_id = documentId.trim();
      setParams(query);
      const response = await axios.get(`${apiUrl}/llm_costs`, { params: query, headers: { "x-api-key": apiKey ?? "" } });
      setReport(response.data);
    } catch (e: any) { setError(e.response?.data?.message ?? "Nie udało się pobrać kosztów LLM"); }
    finally { setLoading(false); }
  }, [apiUrl, apiKey, from, to, documentId, setParams]);

  React.useEffect(() => { void load(); }, []); // initial report only

  const tableStyle: React.CSSProperties = { width: "100%", borderCollapse: "collapse", marginTop: 10 };
  const th: React.CSSProperties = { textAlign: "left", padding: "7px 8px", borderBottom: "1px solid #cbd5e1" };
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid #e2e8f0" };

  return <div>
    <h2>Koszty LLM</h2>
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end", padding: 14, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
      <label>Od<br/><input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label>
      <label>Do<br/><input type="date" value={to} onChange={e => setTo(e.target.value)} /></label>
      <label>Dokument ID (opcjonalnie)<br/><input type="number" min="1" value={documentId} onChange={e => setDocumentId(e.target.value)} placeholder="np. 9258" /></label>
      <button className="button" onClick={load} disabled={loading}>{loading ? "Ładuję…" : "Pokaż"}</button>
      {documentId && <NavLink to={`/chunks/${documentId}`}>Otwórz dokument #{documentId}</NavLink>}
    </div>
    {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
    {report && <>
      <h3>Podsumowanie</h3>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>{report.totals.map((r, i) =>
        <div key={`${r.currency}-${i}`} style={{ padding: 12, minWidth: 190, border: "1px solid #cbd5e1", borderRadius: 8 }}>
          <strong style={{ fontSize: "1.3em" }}>{money(r.cost, r.currency)}</strong><br/>{r.calls} wywołań · {r.tokens.toLocaleString("pl")} tokenów
          {!!r.unknown_calls && <div style={{ color: "#b45309" }}>{r.unknown_calls} bez wyceny</div>}
        </div>)}</div>
      {!report.totals.length && <p>Brak wywołań w wybranym okresie.</p>}
      <h3>Koszt per dokument</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Dokument</th><th style={th}>Koszt</th><th style={th}>Wywołania</th><th style={th}>Tokeny</th><th style={th}>Wycena</th></tr></thead><tbody>
        {report.documents.map((r, i) => <tr key={`${r.document_id ?? "none"}-${r.currency}-${i}`}>
          <td style={td}>{r.document_id != null
            ? <NavLink to={`/chunks/${r.document_id}`}>#{r.document_id} — {r.title || "bez tytułu"}</NavLink>
            : <span style={{ color: "#64748b" }}>Nieprzypisane (starsze lub globalne wywołania)</span>}</td>
          <td style={td}>{money(r.cost, r.currency)}</td><td style={td}>{r.calls}</td><td style={td}>{r.tokens.toLocaleString("pl")}</td>
          <td style={td}>{r.unknown_calls ? <span style={{ color: "#b45309" }}>{r.unknown_calls} bez ceny</span> : "pełna"}</td>
        </tr>)}
      </tbody></table>
      <h3>Koszt dzienny</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Dzień</th><th style={th}>Koszt</th><th style={th}>Wywołania</th><th style={th}>Tokeny</th></tr></thead><tbody>
        {report.daily.map((r, i) => <tr key={`${r.day}-${r.currency}-${i}`}><td style={td}>{r.day}</td><td style={td}>{money(r.cost, r.currency)}</td><td style={td}>{r.calls}</td><td style={td}>{r.tokens.toLocaleString("pl")}</td></tr>)}
      </tbody></table>
      <h3>Modele i operacje</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Operacja</th><th style={th}>Model</th><th style={th}>Koszt</th><th style={th}>Wywołania</th><th style={th}>Tokeny</th></tr></thead><tbody>
        {report.operations.map((r, i) => <tr key={`${r.operation}-${r.model}-${r.currency}-${i}`}><td style={td}>{r.operation}</td><td style={td}>{r.model}</td><td style={td}>{money(r.cost, r.currency)}</td><td style={td}>{r.calls}</td><td style={td}>{r.tokens.toLocaleString("pl")}</td></tr>)}
      </tbody></table>
      {documentId && <><h3>Analizy dokumentu</h3><p style={{ color: "#64748b" }}>Powiązanie obejmuje wywołania wykonane po wdrożeniu tej funkcji.</p>
        <table style={tableStyle}><thead><tr><th style={th}>Data</th><th style={th}>Job / run</th><th style={th}>Koszt</th><th style={th}>Wywołania</th><th style={th}>Tokeny</th></tr></thead><tbody>
          {report.analyses.map((r, i) => <tr key={`${r.job_id}-${r.currency}-${i}`}><td style={td}>{r.started_at?.replace("T", " ").slice(0, 19)}</td><td style={td}>{r.job_id.slice(0, 8)} / {r.run_id ?? "—"}</td><td style={td}>{money(r.cost, r.currency)}</td><td style={td}>{r.calls}</td><td style={td}>{r.tokens.toLocaleString("pl")}</td></tr>)}
        </tbody></table></>}
    </>}
  </div>;
};

export default LlmCosts;
