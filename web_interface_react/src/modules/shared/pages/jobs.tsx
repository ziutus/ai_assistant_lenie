import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type Job = {
  id: string; type: string; status: string; attempt: number; max_attempts: number;
  created_at?: string | null; started_at?: string | null; finished_at?: string | null; watermark?: string | null;
  parameters?: unknown; progress?: unknown; result?: unknown; error?: string | null;
};

const JOBS_REFRESH_INTERVAL_MS = 30_000;
const JOB_TYPES = ["feed_check", "feed_check_all", "feed_auto_import", "feed_daily", "content_group_suggest", "document_prepare", "legacy_aws_pull"];
const JOB_STATUSES = ["queued", "running", "done", "failed", "cancel_requested", "cancelled"];
const formatTime = (value?: string | null) => value ? new Date(value).toLocaleString() : "—";
const statusStyle: Record<string, React.CSSProperties> = {
  queued: { background: "#f1f5f9", color: "#475569" }, running: { background: "#dbeafe", color: "#1d4ed8" },
  done: { background: "#dcfce7", color: "#15803d" }, failed: { background: "#fee2e2", color: "#b91c1c" },
  cancel_requested: { background: "#fef3c7", color: "#92400e" }, cancelled: { background: "#e2e8f0", color: "#475569" },
};
const formatResult = (result: unknown) => {
  if (!result || typeof result !== "object" || Array.isArray(result)) return "—";
  const counters = ["found", "added", "skipped", "refreshed", "errors"].filter((key) => key in result)
    .map((key) => `${key}: ${String((result as Record<string, unknown>)[key])}`);
  return counters.length ? counters.join(" · ") : "zobacz szczegóły";
};

export default function Jobs() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [rows, setRows] = React.useState<Job[]>([]);
  const [canManage, setCanManage] = React.useState(false);
  const [canRunLegacyAwsPull, setCanRunLegacyAwsPull] = React.useState(false);
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(50);
  const [total, setTotal] = React.useState(0);
  const [jobType, setJobType] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [selectedJobId, setSelectedJobId] = React.useState<string | null>(null);
  const [hoveredJobId, setHoveredJobId] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState("");

  const load = React.useCallback(async () => {
    const query = new URLSearchParams({ limit: String(pageSize), offset: String((page - 1) * pageSize) });
    if (jobType) query.set("type", jobType);
    if (status) query.set("status", status);
    const response = await fetch(`${apiUrl}/jobs?${query}`, { headers: { "x-api-key": apiKey || "" } });
    if (!response.ok) { setMessage(`Nie udało się pobrać jobów (${response.status})`); return; }
    const data = await response.json();
    setRows(data.jobs || []); setCanManage(Boolean(data.capabilities?.manage_jobs)); setCanRunLegacyAwsPull(Boolean(data.capabilities?.run_legacy_aws_pull)); setTotal(Number(data.total) || 0);
  }, [apiUrl, apiKey, jobType, page, pageSize, status]);

  const manage = React.useCallback(async (path: string, successMessage: string, body?: unknown) => {
    const response = await fetch(`${apiUrl}${path}`, { method: "POST", headers: { "x-api-key": apiKey || "", ...(body ? { "content-type": "application/json" } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
    if (!response.ok) { setMessage(`Nie udało się wykonać operacji (${response.status})`); return; }
    setMessage(successMessage); await load();
  }, [apiUrl, apiKey, load]);

  React.useEffect(() => { void load(); const timer = window.setInterval(() => void load(), JOBS_REFRESH_INTERVAL_MS); return () => window.clearInterval(timer); }, [load]);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const visiblePages = Array.from({ length: totalPages }, (_, index) => index + 1).filter((number) => number === 1 || number === totalPages || Math.abs(number - page) <= 2);
  const updateFilter = (setter: React.Dispatch<React.SetStateAction<string>>, value: string) => { setter(value); setPage(1); };
  const updatePageSize = (value: number) => { setPageSize(value); setPage(1); };
  const pagination = (position: "top" | "bottom") => totalPages > 1 ? (
    <nav aria-label={`Stronicowanie jobów (${position === "top" ? "góra" : "dół"})`} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, padding: position === "top" ? "14px 0 8px" : "8px 0 30px" }}>
      <button type="button" className="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Poprzednia</button>
      {visiblePages.map((number, index) => <React.Fragment key={number}>{visiblePages[index - 1] && number - visiblePages[index - 1] > 1 && <span>…</span>}<button type="button" className="button" disabled={number === page} aria-current={number === page ? "page" : undefined} style={{ minWidth: 36, opacity: number === page ? .6 : 1 }} onClick={() => setPage(number)}>{number}</button></React.Fragment>)}
      <button type="button" className="button" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Następna</button>
      <label style={{ display: "flex", alignItems: "center", gap: 5, marginLeft: 8 }}>Strona <select value={page} onChange={(event) => setPage(Number(event.target.value))}>{Array.from({ length: totalPages }, (_, index) => index + 1).map((number) => <option key={number} value={number}>{number}</option>)}</select> z {totalPages}</label>
    </nav>
  ) : null;

  return <section>
    <h2 style={{ marginBottom: "20px" }}>Joby ({rows.length} z {total})</h2>
    <label>Typ <select value={jobType} onChange={(event) => updateFilter(setJobType, event.target.value)}><option value="">Wszystkie</option>{JOB_TYPES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
    <label style={{ marginLeft: 12 }}>Status <select value={status} onChange={(event) => updateFilter(setStatus, event.target.value)}><option value="">Wszystkie</option>{JOB_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
    <label style={{ marginLeft: 12 }}>Wyników na stronę <select value={pageSize} onChange={(event) => updatePageSize(Number(event.target.value))}>{[25, 50, 100].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
    <button type="button" className="button" style={{ marginLeft: 12 }} onClick={() => void load()}>Odśwież</button>
    {canRunLegacyAwsPull && <button type="button" className="button" style={{ marginLeft: 6 }} onClick={() => void manage("/jobs", "Zlecono legacy_aws_pull", { type: "legacy_aws_pull" })}>Uruchom legacy_aws_pull</button>}
    {message && <p className="errorText" role="alert">{message}</p>}
    {pagination("top")}
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1200 }}>
        <thead style={{ background: "#f1f5f9", color: "#475569" }}><tr>{["Typ", "Status", "Próba", "Utworzono", "Start", "Koniec", "Watermark", "Wynik", "Szczegóły", "Akcje"].map((label) => <th key={label} style={{ padding: "10px 8px", textAlign: "left", borderBottom: "1px solid rgb(179, 179, 179)", whiteSpace: "nowrap" }}>{label}</th>)}</tr></thead>
        <tbody>{rows.map((job) => {
          const selected = selectedJobId === job.id;
          const hovered = hoveredJobId === job.id;
          return <tr key={job.id} onClick={() => setSelectedJobId(job.id)} onMouseEnter={() => setHoveredJobId(job.id)} onMouseLeave={() => setHoveredJobId(null)} style={{ borderBottom: "1px solid rgb(179, 179, 179)", background: selected ? "#dbeafe" : hovered ? "#f1f5f9" : undefined, cursor: "pointer" }}>
          <td style={{ padding: "10px 8px" }}>{job.type}</td><td style={{ padding: "10px 8px" }}><span style={{ ...statusStyle[job.status], borderRadius: 10, padding: "2px 7px", fontSize: ".85em", fontWeight: 500 }}>{job.status}</span></td><td style={{ padding: "10px 8px" }}>{job.attempt}/{job.max_attempts}</td><td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>{formatTime(job.created_at)}</td><td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>{formatTime(job.started_at)}</td><td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>{formatTime(job.finished_at)}</td><td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>{job.watermark || "—"}</td><td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>{formatResult(job.result)}</td><td style={{ padding: "10px 8px" }}><details><summary>JSON</summary><pre>{JSON.stringify(job.error || job.result || job.progress || job.parameters || "—", null, 2)}</pre></details></td><td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>{canManage && job.status === "failed" && job.attempt < job.max_attempts && <button type="button" className="button" onClick={() => void manage(`/jobs/${job.id}/retry`, "Zlecono retry")}>Retry</button>}{canManage && (job.status === "queued" || job.status === "running") && <button type="button" className="button" onClick={() => void manage(`/jobs/${job.id}/cancel`, "Zlecono anulowanie")}>Anuluj</button>}</td>
        </tr>;
        })}{!rows.length && <tr><td colSpan={10} style={{ padding: "10px 8px" }}>Brak jobów</td></tr>}</tbody>
      </table>
    </div>
    {pagination("bottom")}
  </section>;
}
