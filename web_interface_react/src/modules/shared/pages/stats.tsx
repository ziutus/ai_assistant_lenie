import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

type TypeRow = { document_type: string; count: number };
type StateRow = { processing_status: string; count: number };
type SourceRow = { name: string; count: number };
type DailyRow = { day: string; count: number };
type RecentRow = {
  id: number; title: string | null; document_type: string; processing_status: string;
  source: string; ingested_at: string | null;
};
type StatsReport = {
  total: number; by_type: TypeRow[]; by_state: StateRow[]; by_source: SourceRow[];
  daily: DailyRow[]; recent: RecentRow[];
};

const DAYS = 30;

const Stats = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [report, setReport] = React.useState<StatsReport | null>(null);
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await axios.get(`${apiUrl}/stats`, { params: { days: DAYS }, headers: { "x-api-key": apiKey ?? "" } });
      setReport(response.data);
    } catch (e: any) { setError(e.response?.data?.message ?? "Nie udało się pobrać statystyk"); }
    finally { setLoading(false); }
  }, [apiUrl, apiKey]);

  React.useEffect(() => { void load(); }, [load]);

  const tableStyle: React.CSSProperties = { width: "100%", borderCollapse: "collapse", marginTop: 10 };
  const th: React.CSSProperties = { textAlign: "left", padding: "7px 8px", borderBottom: "1px solid #cbd5e1" };
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid #e2e8f0" };

  const maxDaily = report ? Math.max(1, ...report.daily.map(d => d.count)) : 1;

  return <div>
    <h2>Statystyki dokumentów</h2>
    {loading && <p>Ładuję…</p>}
    {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
    {report && <>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div style={{ padding: 12, minWidth: 190, border: "1px solid #cbd5e1", borderRadius: 8 }}>
          <strong style={{ fontSize: "1.3em" }}>{report.total.toLocaleString("pl")}</strong><br/>wszystkich dokumentów
        </div>
        {report.by_type.map(r => <div key={r.document_type} style={{ padding: 12, minWidth: 190, border: "1px solid #cbd5e1", borderRadius: 8 }}>
          <strong style={{ fontSize: "1.3em" }}>{r.count.toLocaleString("pl")}</strong><br/>{r.document_type}
        </div>)}
      </div>

      <h3>Ostatnie {DAYS} dni</h3>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 120, padding: "8px 4px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
        {report.daily.map((d, i) => <div key={d.day} title={`${d.day}: ${d.count}`}
          style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center" }}>
          <div style={{ width: "100%", background: "#2563eb", borderRadius: 2, height: `${(d.count / maxDaily) * 90}px`, minHeight: d.count ? 2 : 0 }} />
          {i % 5 === 0 && <span style={{ fontSize: 10, color: "#64748b", marginTop: 4, writingMode: "vertical-rl" }}>{d.day.slice(5)}</span>}
        </div>)}
      </div>

      <h3>Wg stanu przetwarzania</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Stan</th><th style={th}>Liczba</th></tr></thead><tbody>
        {report.by_state.map(r => <tr key={r.processing_status}><td style={td}>{r.processing_status}</td><td style={td}>{r.count}</td></tr>)}
      </tbody></table>

      <h3>Wg źródła</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Źródło</th><th style={th}>Liczba</th></tr></thead><tbody>
        {report.by_source.map(r => <tr key={r.name}><td style={td}>{r.name}</td><td style={td}>{r.count}</td></tr>)}
      </tbody></table>

      <h3>Ostatnio dodane</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Dodano</th><th style={th}>Tytuł</th><th style={th}>Typ</th><th style={th}>Stan</th><th style={th}>Źródło</th></tr></thead><tbody>
        {report.recent.map(r => <tr key={r.id}>
          <td style={td}>{r.ingested_at?.replace("T", " ").slice(0, 19) ?? "—"}</td>
          <td style={td}><NavLink to={`/chunks/${r.id}`}>#{r.id} — {r.title || "bez tytułu"}</NavLink></td>
          <td style={td}>{r.document_type}</td><td style={td}>{r.processing_status}</td><td style={td}>{r.source}</td>
        </tr>)}
      </tbody></table>
      {!report.recent.length && <p>Brak dokumentów.</p>}
    </>}
  </div>;
};

export default Stats;
