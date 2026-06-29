import React from "react";
import { useParams, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

interface Chunk {
  id: number;
  order_index: number;
  text: string;
  corrected_text: string | null;
  summary: string | null;
  topic: string | null;
  chunk_type: string | null;
  speaker: string | null;
}

interface AnalysisRun {
  id: number;
  model: string;
  created_at: string;
  chunk_count: number;
}

const MODELS = [
  "Bielik-11B-v3.0-Instruct",
  "Bielik-4.5B-v3.0-Instruct",
  "gpt-4o-mini",
  "gpt-4o",
];

const Chunks = () => {
  const { id } = useParams<{ id: string }>();
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);

  const [runs, setRuns] = React.useState<AnalysisRun[]>([]);
  const [selectedRun, setSelectedRun] = React.useState<number | null>(null);
  const [chunks, setChunks] = React.useState<Chunk[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [jobStatus, setJobStatus] = React.useState<string | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [newModel, setNewModel] = React.useState(MODELS[0]);
  const [chunkSize, setChunkSize] = React.useState(5000);
  const [showRaw, setShowRaw] = React.useState<Record<number, boolean>>({});

  const headers = { "x-api-key": apiKey ?? "", "Content-Type": "application/json" };

  const fetchRuns = React.useCallback(async () => {
    if (!id) return;
    try {
      const r = await fetch(`${apiUrl}/analysis_runs?doc_id=${id}`, { headers });
      const data = await r.json();
      const list: AnalysisRun[] = data.runs ?? [];
      setRuns(list);
      if (list.length > 0 && selectedRun === null) {
        setSelectedRun(list[0].id);
      }
    } catch {
      setError("Błąd ładowania listy analiz");
    }
  }, [id, apiUrl, apiKey]);

  const fetchChunks = React.useCallback(async (runId: number) => {
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${runId}/chunks`, { headers });
      const data = await r.json();
      setChunks(data.chunks ?? []);
    } catch {
      setError("Błąd ładowania chunków");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, apiKey]);

  React.useEffect(() => { fetchRuns(); }, [fetchRuns]);

  React.useEffect(() => {
    if (selectedRun !== null) fetchChunks(selectedRun);
  }, [selectedRun, fetchChunks]);

  const pollJob = React.useCallback((jid: string) => {
    const interval = setInterval(async () => {
      try {
        const r = await fetch(`${apiUrl}/analysis_job/${jid}`, { headers });
        const data = await r.json();
        setJobStatus(data.status);
        if (data.status === "done") {
          clearInterval(interval);
          setJobId(null);
          await fetchRuns();
          if (data.run_id) {
            setSelectedRun(data.run_id);
          }
        } else if (data.status === "failed") {
          clearInterval(interval);
          setJobId(null);
          setError("Analiza nie powiodła się: " + (data.error ?? ""));
        }
      } catch {
        clearInterval(interval);
        setJobId(null);
      }
    }, 5000);
  }, [apiUrl, apiKey, fetchRuns]);

  const startAnalysis = async () => {
    if (!id) return;
    setError("");
    setJobStatus("starting");
    try {
      const r = await fetch(`${apiUrl}/document/${id}/analyze_chunks`, {
        method: "POST",
        headers,
        body: JSON.stringify({ model: newModel, chunk_size: chunkSize }),
      });
      const data = await r.json();
      if (data.job_id) {
        setJobId(data.job_id);
        setJobStatus("running");
        pollJob(data.job_id);
      } else {
        setError("Nie udało się uruchomić analizy");
        setJobStatus(null);
      }
    } catch {
      setError("Błąd połączenia");
      setJobStatus(null);
    }
  };

  const toggleRaw = (chunkId: number) => {
    setShowRaw(prev => ({ ...prev, [chunkId]: !prev[chunkId] }));
  };

  const docType = chunks.length > 0 ? null : null;

  return (
    <div style={{ maxWidth: 900 }}>
      <h2 style={{ marginBottom: 6 }}>
        Przegląd chunków — dokument #{id}
      </h2>
      <NavLink to={`/youtube/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>
        ← Edytuj dokument
      </NavLink>

      {/* Nowa analiza */}
      <div style={{ margin: "20px 0", padding: "14px 16px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
        <strong style={{ fontSize: "0.9em" }}>Nowa analiza</strong>
        <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap", alignItems: "center" }}>
          <select value={newModel} onChange={e => setNewModel(e.target.value)} style={{ padding: "5px 8px", fontSize: "0.88em" }}>
            {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <label style={{ fontSize: "0.85em" }}>
            Rozmiar chunka:&nbsp;
            <input
              type="number"
              value={chunkSize}
              onChange={e => setChunkSize(Number(e.target.value))}
              style={{ width: 80, padding: "4px 6px", fontSize: "0.88em" }}
              min={500}
              max={20000}
              step={500}
            />
          </label>
          <button
            className="button"
            onClick={startAnalysis}
            disabled={!!jobId}
          >
            {jobId ? `Analiza… (${jobStatus})` : "Uruchom analizę"}
          </button>
        </div>
      </div>

      {/* Wybór runu */}
      {runs.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: "0.85em", fontWeight: 600 }}>Analiza: </label>
          <select
            value={selectedRun ?? ""}
            onChange={e => setSelectedRun(Number(e.target.value))}
            style={{ padding: "4px 8px", fontSize: "0.88em" }}
          >
            {runs.map(r => (
              <option key={r.id} value={r.id}>
                #{r.id} — {r.model} ({r.chunk_count} chunków, {new Date(r.created_at).toLocaleString("pl")})
              </option>
            ))}
          </select>
        </div>
      )}

      {error && <p style={{ color: "#dc2626", marginBottom: 12 }}>{error}</p>}
      {loading && <div className="loader" style={{ marginBottom: 12 }} />}

      {/* Chunki */}
      {chunks.map((chunk, i) => {
        const hasCorrected = !!chunk.corrected_text;
        const isShowingRaw = showRaw[chunk.id] ?? false;
        const displayText = (!hasCorrected || isShowingRaw) ? chunk.text : chunk.corrected_text!;

        return (
          <div key={chunk.id} style={{ marginBottom: 20, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
            {/* Nagłówek chunka */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px", background: "#f1f5f9", borderBottom: "1px solid #e2e8f0", fontSize: "0.82em", color: "#64748b" }}>
              <span style={{ fontWeight: 600, color: "#334155" }}>#{i + 1}</span>
              {chunk.topic && <span style={{ background: "#dbeafe", color: "#1d4ed8", padding: "1px 8px", borderRadius: 4 }}>{chunk.topic}</span>}
              {chunk.chunk_type && chunk.chunk_type !== "NORMAL" && (
                <span style={{ background: chunk.chunk_type === "REKLAMA" ? "#fee2e2" : "#fef9c3", color: chunk.chunk_type === "REKLAMA" ? "#991b1b" : "#854d0e", padding: "1px 8px", borderRadius: 4 }}>
                  {chunk.chunk_type}
                </span>
              )}
              {chunk.speaker && <span>🎙 {chunk.speaker}</span>}
              <span style={{ marginLeft: "auto" }}>
                {hasCorrected && (
                  <button
                    onClick={() => toggleRaw(chunk.id)}
                    style={{ fontSize: "0.9em", padding: "2px 10px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer" }}
                  >
                    {isShowingRaw ? "Pokaż poprawiony" : "Pokaż surowy"}
                  </button>
                )}
              </span>
            </div>

            {/* Treść */}
            <div style={{ padding: "12px 14px", fontSize: "0.9em", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
              {displayText}
            </div>

            {/* Podsumowanie */}
            {chunk.summary && (
              <div style={{ padding: "10px 14px", background: "#f8fafc", borderTop: "1px solid #e2e8f0", fontSize: "0.85em", color: "#475569" }}>
                <span style={{ fontWeight: 600, color: "#64748b", fontSize: "0.8em", textTransform: "uppercase", letterSpacing: "0.05em" }}>Podsumowanie</span>
                <p style={{ margin: "4px 0 0", lineHeight: 1.5 }}>{chunk.summary}</p>
              </div>
            )}
          </div>
        );
      })}

      {!loading && chunks.length === 0 && runs.length === 0 && (
        <p style={{ color: "#64748b", fontStyle: "italic" }}>Brak analiz dla tego dokumentu. Uruchom pierwszą analizę powyżej.</p>
      )}
    </div>
  );
};

export default Chunks;
