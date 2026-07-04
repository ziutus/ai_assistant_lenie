import React from "react";
import { useParams, useLocation, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// ── Types ────────────────────────────────────────────────────────────────────

interface Segment {
  start: number;
  text: string;
}

interface Chunk {
  id: number;
  position: number;
  original_text: string | null;
  corrected_text: string | null;
  summary: string | null;
  topic: string | null;
  type: string | null;
  speaker: string | null;
  status: string;
  seg_start: number | null;
  seg_end: number | null;
}

interface Speaker {
  name: string;
  role: string | null;
}

interface AnalysisRun {
  id: number;
  model: string;
  created_at: string;
  chunk_count: number;
  mode: string;
  status: string;
  scope: string | null;
}

const RUN_STATUS_LABELS: Record<string, string> = {
  created: "nowa",
  in_review: "w przeglądzie",
  reviewed: "zamknięta",
};

type ChunkType = "TEMAT" | "REKLAMA" | "SZUM";

interface SplitState {
  segIdx: number;
  ts: string;
  firstType: ChunkType;
  secondType: ChunkType;
}

interface LineSplitState {
  lineIdx: number;
  firstType: ChunkType;
  secondType: ChunkType;
}

interface SegGroup {
  absIdx: number;
  start: number;
  text: string;
  isSpeakerChange: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const MODELS = [
  "Bielik-11B-v3.0-Instruct",
  "Bielik-4.5B-v3.0-Instruct",
  "gpt-4o-mini",
  "gpt-4o",
];

const STATUS_CYCLE = ["pending", "approved", "needs_reanalysis"] as const;
const TYPE_CYCLE: ChunkType[] = ["TEMAT", "REKLAMA", "SZUM"];

function typeColor(type: string | null): React.CSSProperties {
  switch (type) {
    case "REKLAMA": return { background: "#fee2e2", color: "#991b1b" };
    case "SZUM":    return { background: "#e5e7eb", color: "#4b5563" };
    default:        return { background: "#dbeafe", color: "#1d4ed8" };
  }
}

function secs2ts(s: number): string {
  s = Math.floor(s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${String(h).padStart(2, "0")}:${mm}:${ss}` : `${mm}:${ss}`;
}

function groupSegments(segs: Segment[], absOffset: number): SegGroup[] {
  const MAX = 8;
  const groups: SegGroup[] = [];
  let curTexts: string[] = [];
  let curStart: number | null = null;
  let curIsSc = false;
  let curFirstRawIdx = 0;

  function flush() {
    if (curTexts.length > 0 && curStart !== null) {
      groups.push({ absIdx: absOffset + curFirstRawIdx, start: curStart, text: curTexts.join(" "), isSpeakerChange: curIsSc });
      curTexts = []; curStart = null; curIsSc = false;
    }
  }

  segs.forEach((seg, rawIdx) => {
    const raw = (seg.text || "").trim();
    if (!raw) return;
    const isSc = raw.startsWith(">>");
    const text = isSc ? raw.slice(2).trim() : raw;
    if (isSc && curTexts.length > 0) flush();
    if (curStart === null) { curStart = seg.start; curIsSc = isSc; curFirstRawIdx = rawIdx; }
    curTexts.push(text);
    if (/[.?!…]$/.test(text) || curTexts.length >= MAX) flush();
  });
  flush();
  return groups;
}

function statusColor(status: string): React.CSSProperties {
  switch (status) {
    case "approved":         return { background: "#dcfce7", color: "#15803d" };
    case "needs_reanalysis": return { background: "#fee2e2", color: "#b91c1c" };
    case "split_requested":  return { background: "#fef9c3", color: "#713f12" };
    default:                 return { background: "#e2e8f0", color: "#475569" };
  }
}

// ── Segments sub-component ───────────────────────────────────────────────────

const SegmentsView: React.FC<{
  segs: Segment[];
  videoId: string;
  chunkId: number;
  absOffset: number;
  splitState: SplitState | undefined;
  onMarkSplit: (chunkId: number, absIdx: number, ts: string) => void;
}> = ({ segs, videoId, chunkId, absOffset, splitState, onMarkSplit }) => {
  const groups = groupSegments(segs, absOffset);
  if (groups.length === 0) return <em style={{ color: "#94a3b8" }}>brak segmentów</em>;

  return (
    <div>
      {groups.map(g => {
        const ts = secs2ts(g.start);
        const ytUrl = videoId ? `https://www.youtube.com/watch?v=${videoId}&t=${Math.floor(g.start)}` : undefined;
        const isMarked = splitState?.segIdx === g.absIdx;
        return (
          <div
            key={g.absIdx}
            style={{
              position: "relative", marginBottom: 8, paddingRight: 32,
              ...(isMarked ? { background: "#fff7ed", borderLeft: "3px solid #f97316", paddingLeft: 6, borderRadius: 2 } : {}),
            }}
          >
            <div style={{ fontSize: "0.8em", color: "#94a3b8", marginBottom: 1 }}>
              {g.isSpeakerChange && <span style={{ marginRight: 4 }}>▶</span>}
              {ytUrl ? (
                <a href={ytUrl} target="_blank" rel="noopener noreferrer"
                  style={{ color: "#c00", fontWeight: "bold", textDecoration: "none" }}>
                  [{ts}]
                </a>
              ) : (
                <span>[{ts}]</span>
              )}
            </div>
            <span style={{ fontSize: "0.88em", lineHeight: 1.6 }}>{g.text}</span>
            <button
              onClick={() => onMarkSplit(chunkId, g.absIdx, ts)}
              title="Podziel tutaj"
              style={{
                position: "absolute", right: 2, top: 2,
                background: "none", border: "1px solid #e2e8f0", borderRadius: 3,
                fontSize: "0.82em", cursor: "pointer", padding: "1px 5px", color: "#94a3b8",
              }}
              onMouseEnter={e => { e.currentTarget.style.background = "#fef3c7"; e.currentTarget.style.color = "#92400e"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "none"; e.currentTarget.style.color = "#94a3b8"; }}
            >
              ✂
            </button>
          </div>
        );
      })}
    </div>
  );
};

// ── Plain-text view with line removal (article chunks) ──────────────────────

const PlainTextLines: React.FC<{
  text: string;
  markedLines: Set<number>;
  splitLineIdx: number | null;
  saving: boolean;
  onToggleLine: (idx: number) => void;
  onMarkSplit: (idx: number) => void;
  onSave: (removeFromDocument: boolean) => void;
  onCancel: () => void;
}> = ({ text, markedLines, splitLineIdx, saving, onToggleLine, onMarkSplit, onSave, onCancel }) => {
  const [removeFromDoc, setRemoveFromDoc] = React.useState(true);
  if (!text) return <em style={{ color: "#94a3b8" }}>brak tekstu</em>;
  const lines = text.split("\n");
  const lineBtnStyle: React.CSSProperties = {
    background: "none", border: "1px solid #e2e8f0", borderRadius: 3,
    fontSize: "0.78em", cursor: "pointer", padding: "0 4px", lineHeight: "1.3em",
  };
  return (
    <div>
      {lines.map((line, i) => {
        const marked = markedLines.has(i);
        const isSplitMark = splitLineIdx === i;
        return (
          <div
            key={i}
            style={{
              position: "relative", paddingLeft: 56, borderRadius: 2, minHeight: "1.4em",
              ...(marked ? { background: "#fee2e2", textDecoration: "line-through", color: "#991b1b" } : {}),
              ...(isSplitMark ? { background: "#fff7ed", borderLeft: "3px solid #f97316" } : {}),
            }}
          >
            <span style={{ position: "absolute", left: 0, top: 1, display: "flex", gap: 3 }}>
              <button
                onClick={() => onToggleLine(i)}
                title={marked ? "Przywróć linię" : "Usuń linię"}
                style={{ ...lineBtnStyle, color: marked ? "#991b1b" : "#94a3b8" }}
              >
                {marked ? "↺" : "✕"}
              </button>
              {i > 0 && (
                <button
                  onClick={() => onMarkSplit(i)}
                  title="Podziel tutaj — ta linia zacznie nowy chunk"
                  style={{ ...lineBtnStyle, color: isSplitMark ? "#92400e" : "#94a3b8", fontWeight: isSplitMark ? "bold" : "normal" }}
                >
                  ✂
                </button>
              )}
            </span>
            <span style={{ whiteSpace: "pre-wrap" }}>{line || " "}</span>
          </div>
        );
      })}
      {markedLines.size > 0 && (
        <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button onClick={() => onSave(removeFromDoc)} disabled={saving}
            style={{ padding: "3px 12px", background: "#b91c1c", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer", fontWeight: "bold", fontSize: "0.85em" }}>
            {saving ? "Zapisuję…" : `Usuń ${markedLines.size} ${markedLines.size === 1 ? "linię" : "linie/linii"} i zapisz`}
          </button>
          <button onClick={onCancel}
            style={{ padding: "3px 10px", background: "#e2e8f0", color: "#475569", border: "none", borderRadius: 3, cursor: "pointer", fontSize: "0.85em" }}>
            Anuluj
          </button>
          <label style={{ fontSize: "0.8em", color: "#475569", display: "flex", alignItems: "center", gap: 4 }}
            title="Usuwa wszystkie wystąpienia tych linii z pól text/text_md dokumentu — kolejne analizy startują z czystego tekstu">
            <input type="checkbox" checked={removeFromDoc} onChange={e => setRemoveFromDoc(e.target.checked)} />
            usuń też z dokumentu źródłowego (wszystkie wystąpienia)
          </label>
          <span style={{ fontSize: "0.8em", color: "#94a3b8" }}>
            Po zapisie warto ponownie uruchomić analizę chunka (▶ Pełna), by odświeżyć temat i streszczenie.
          </span>
        </div>
      )}
    </div>
  );
};

// ── Main component ───────────────────────────────────────────────────────────

const Chunks = () => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const initialDocType = (location.state as { docType?: string } | null)?.docType ?? "";
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);

  const [runs, setRuns]             = React.useState<AnalysisRun[]>([]);
  const [selectedRun, setSelectedRun] = React.useState<number | null>(null);
  const [chunks, setChunks]         = React.useState<Chunk[]>([]);
  const [segments, setSegments]     = React.useState<Segment[]>([]);
  const [videoId, setVideoId]       = React.useState("");
  const [docType, setDocType]       = React.useState(initialDocType);
  const [runMode, setRunMode]       = React.useState("transcript");
  const [speakers, setSpeakers]     = React.useState<Speaker[]>([]);

  const [loading, setLoading]       = React.useState(false);
  const [error, setError]           = React.useState("");
  const [info, setInfo]             = React.useState("");
  const [applyingCleanup, setApplyingCleanup] = React.useState(false);
  const [jobStatus, setJobStatus]   = React.useState<string | null>(null);
  const [jobId, setJobId]           = React.useState<string | null>(null);
  const [newModel, setNewModel]     = React.useState(MODELS[0]);
  const [newMode, setNewMode]       = React.useState("transcript");
  const [splitOnly, setSplitOnly]   = React.useState(false);
  const [chunkSize, setChunkSize]   = React.useState(5000);
  const [splitPreview, setSplitPreview] = React.useState<{ count: number; sizes: number[]; length: number } | null>(null);
  const [previewNonce, setPreviewNonce] = React.useState(0);
  const [hideAds, setHideAds]       = React.useState(false);

  const [showCorrected, setShowCorrected] = React.useState<Record<number, boolean>>({});
  const [topicEdits, setTopicEdits]       = React.useState<Record<number, string>>({});
  const [savingTopics, setSavingTopics]   = React.useState<Record<number, boolean>>({});
  const [savedFlash, setSavedFlash]       = React.useState<Record<number, boolean>>({});
  const [reanalyzing, setReanalyzing]     = React.useState<Record<number, boolean>>({});
  const [reanalyzingAll, setReanalyzingAll] = React.useState(false);
  const [approvingAll, setApprovingAll] = React.useState(false);
  const [splitStates, setSplitStates]     = React.useState<Record<number, SplitState>>({});
  const [lineEdits, setLineEdits]         = React.useState<Record<number, Set<number>>>({});
  const [savingLines, setSavingLines]     = React.useState<Record<number, boolean>>({});
  const [lineSplitStates, setLineSplitStates] = React.useState<Record<number, LineSplitState>>({});
  const [confirmingLineSplit, setConfirmingLineSplit] = React.useState<Record<number, boolean>>({});
  const [confirmingSplit, setConfirmingSplit] = React.useState<Record<number, boolean>>({});
  const [extractingSpeakers, setExtractingSpeakers] = React.useState(false);
  const [hiddenChunks, setHiddenChunks] = React.useState<Set<number>>(new Set());

  const headers = { "x-api-key": apiKey ?? "", "Content-Type": "application/json" };

  // ── Fetch ──

  const fetchRuns = React.useCallback(async () => {
    if (!id) return;
    try {
      const r = await fetch(`${apiUrl}/analysis_runs?doc_id=${id}`, { headers });
      const data = await r.json();
      const list: AnalysisRun[] = data.runs ?? [];
      setRuns(list);
      if (list.length > 0 && selectedRun === null) setSelectedRun(list[0].id);
    } catch {
      setError("Błąd ładowania listy analiz");
    }
  }, [id, apiUrl, apiKey]);

  const fetchChunks = React.useCallback(async (runId: number) => {
    setLoading(true);
    setError("");
    setInfo("");
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${runId}/chunks`, { headers });
      const data = await r.json();
      const loaded: Chunk[] = data.chunks ?? [];
      setChunks(loaded);
      setSegments(data.segments ?? []);
      setVideoId(data.document?.original_id ?? "");
      setDocType(data.document?.document_type ?? "");
      setRunMode(data.run?.mode ?? "transcript");
      setSpeakers(data.run?.speakers ?? []);
      const edits: Record<number, string> = {};
      const correctedDefaults: Record<number, boolean> = {};
      loaded.forEach(c => {
        edits[c.id] = c.topic ?? "";
        correctedDefaults[c.id] = !!c.corrected_text;
      });
      setTopicEdits(edits);
      setShowCorrected(correctedDefaults);
      setSplitStates({});
      setLineEdits({});
      setLineSplitStates({});
      setHiddenChunks(new Set());
    } catch {
      setError("Błąd ładowania chunków");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, apiKey]);

  React.useEffect(() => { fetchRuns(); }, [fetchRuns]);
  React.useEffect(() => { if (selectedRun !== null) fetchChunks(selectedRun); }, [selectedRun, fetchChunks]);
  // Clean documents (articles, webpages) default to article mode for new analyses
  React.useEffect(() => {
    if (docType && docType !== "youtube" && docType !== "movie") setNewMode("article");
  }, [docType]);

  // Live preview: how many chunks would a new split produce (no LLM, debounced)
  React.useEffect(() => {
    if (!id) return;
    const t = setTimeout(async () => {
      try {
        const r = await fetch(
          `${apiUrl}/document/${id}/split_preview?mode=${newMode}&chunk_size=${chunkSize}`,
          { headers: { "x-api-key": apiKey ?? "" } },
        );
        const data = await r.json();
        if (data.status === "success") {
          setSplitPreview({ count: data.chunk_count, sizes: data.chunk_sizes, length: data.text_length });
        } else {
          setSplitPreview(null);
        }
      } catch { setSplitPreview(null); }
    }, 400);
    return () => clearTimeout(t);
  }, [id, newMode, chunkSize, apiUrl, apiKey, previewNonce]);

  // ── Job polling ──

  const pollJob = React.useCallback((jid: string) => {
    const interval = setInterval(async () => {
      try {
        const r = await fetch(`${apiUrl}/analysis_job/${jid}`, { headers });
        const data = await r.json();
        setJobStatus(data.job?.status ?? data.status);
        if (data.job?.status === "done") {
          clearInterval(interval);
          setJobId(null);
          await fetchRuns();
          if (data.job.run_id) setSelectedRun(data.job.run_id);
        } else if (data.job?.status === "failed") {
          clearInterval(interval);
          setJobId(null);
          setError("Analiza nie powiodła się: " + (data.job.error ?? ""));
        }
      } catch {
        clearInterval(interval);
        setJobId(null);
      }
    }, 5000);
  }, [apiUrl, apiKey, fetchRuns]);

  // ── Analysis ──

  const startAnalysis = async (modeOverride?: string, splitOnlyOverride?: boolean) => {
    if (!id) return;
    setError(""); setJobStatus("starting");
    try {
      const r = await fetch(`${apiUrl}/document/${id}/analyze_chunks`, {
        method: "POST", headers,
        body: JSON.stringify({
          model: newModel, chunk_size: chunkSize,
          mode: modeOverride ?? newMode,
          split_only: splitOnlyOverride ?? splitOnly,
        }),
      });
      const data = await r.json();
      if (data.job_id) { setJobId(data.job_id); setJobStatus("running"); pollJob(data.job_id); }
      else { setError("Nie udało się uruchomić analizy"); setJobStatus(null); }
    } catch { setError("Błąd połączenia"); setJobStatus(null); }
  };

  // ── Chunk patch ──

  const patchChunk = async (chunkId: number, updates: Record<string, unknown>) => {
    try {
      const r = await fetch(`${apiUrl}/chunk/${chunkId}`, {
        method: "PATCH", headers, body: JSON.stringify(updates),
      });
      const data = await r.json();
      if (data.status === "success") {
        setChunks(prev => prev.map(c => c.id === chunkId ? { ...c, ...data.chunk } : c));
      }
      return data;
    } catch {
      setError("Błąd zapisu"); return null;
    }
  };

  const saveTopic = async (chunkId: number) => {
    setSavingTopics(prev => ({ ...prev, [chunkId]: true }));
    const res = await patchChunk(chunkId, { topic: topicEdits[chunkId] || null });
    setSavingTopics(prev => ({ ...prev, [chunkId]: false }));
    if (res?.status === "success") {
      setSavedFlash(prev => ({ ...prev, [chunkId]: true }));
      setTimeout(() => setSavedFlash(prev => ({ ...prev, [chunkId]: false })), 1500);
    }
  };

  const cycleStatus = (chunk: Chunk) => {
    const idx = STATUS_CYCLE.indexOf(chunk.status as typeof STATUS_CYCLE[number]);
    const next = STATUS_CYCLE[(idx + 1) % STATUS_CYCLE.length];
    patchChunk(chunk.id, { status: next });
  };

  const toggleType = (chunk: Chunk) => {
    const idx = TYPE_CYCLE.indexOf(chunk.type as ChunkType);
    patchChunk(chunk.id, { type: TYPE_CYCLE[(idx + 1) % TYPE_CYCLE.length] });
  };

  // ── Re-analysis ──

  const reanalyzeChunk = async (chunkId: number, mode: "full" | "semantic") => {
    setReanalyzing(prev => ({ ...prev, [chunkId]: true }));
    try {
      const r = await fetch(`${apiUrl}/chunk/${chunkId}/reanalyze`, {
        method: "POST", headers, body: JSON.stringify({ mode }),
      });
      const data = await r.json();
      if (data.status === "success") {
        setChunks(prev => prev.map(c => c.id === chunkId ? { ...c, ...data.chunk } : c));
        setTopicEdits(prev => ({ ...prev, [chunkId]: data.chunk.topic ?? "" }));
        setShowCorrected(prev => ({ ...prev, [chunkId]: !!data.chunk.corrected_text }));
      } else { setError("Błąd re-analizy"); }
    } catch { setError("Błąd połączenia przy re-analizie"); }
    finally { setReanalyzing(prev => ({ ...prev, [chunkId]: false })); }
  };

  // Chunks that still need an LLM pass: flagged for re-analysis OR fresh from
  // a split-only run (pending TEMAT without a summary)
  const chunksToAnalyze = chunks.filter(c =>
    c.status === "needs_reanalysis"
    || (c.type === "TEMAT" && c.status === "pending" && !c.summary)
  );

  const reanalyzeAll = async () => {
    if (!chunksToAnalyze.length) return;
    setReanalyzingAll(true);
    for (const chunk of chunksToAnalyze) {
      await reanalyzeChunk(chunk.id, chunk.corrected_text ? "semantic" : "full");
    }
    setReanalyzingAll(false);
  };

  const approveAll = async () => {
    const toApprove = chunks.filter(c => c.type === "TEMAT" && c.status !== "approved");
    if (!toApprove.length) return;
    setApprovingAll(true);
    try {
      await Promise.all(toApprove.map(c => patchChunk(c.id, { status: "approved" })));
    } finally {
      setApprovingAll(false);
    }
  };

  // ── Line removal (article chunks) ──

  const toggleLineMark = (chunkId: number, idx: number) => {
    setLineEdits(prev => {
      const cur = new Set(prev[chunkId] ?? []);
      if (cur.has(idx)) {
        cur.delete(idx);
      } else {
        cur.add(idx);
      }
      return { ...prev, [chunkId]: cur };
    });
  };

  const clearLineMarks = (chunkId: number) => {
    setLineEdits(prev => { const n = { ...prev }; delete n[chunkId]; return n; });
  };

  const saveLineRemovals = async (chunk: Chunk, removeFromDocument: boolean) => {
    const marked = lineEdits[chunk.id];
    if (!marked || marked.size === 0) return;
    const lines = (chunk.original_text ?? "").split("\n");
    const newText = lines.filter((_, i) => !marked.has(i)).join("\n");
    if (!newText.trim()) { setError("Nie można usunąć wszystkich linii"); return; }
    const removedLines = lines.filter((_, i) => marked.has(i)).map(l => l.trim()).filter(Boolean);
    setSavingLines(prev => ({ ...prev, [chunk.id]: true }));
    const res = await patchChunk(chunk.id, {
      original_text: newText,
      ...(removeFromDocument && removedLines.length ? { remove_lines_from_document: removedLines } : {}),
    });
    setSavingLines(prev => ({ ...prev, [chunk.id]: false }));
    if (res?.status === "success") {
      clearLineMarks(chunk.id);
      if (res.document_lines_removed > 0) {
        setInfo(`Usunięto ${res.document_lines_removed} linii z dokumentu źródłowego`);
        setPreviewNonce(n => n + 1);
      }
    }
  };

  const markLineSplit = (chunkId: number, lineIdx: number) => {
    setLineSplitStates(prev => {
      if (prev[chunkId]?.lineIdx === lineIdx) {
        const n = { ...prev }; delete n[chunkId]; return n;  // click again = unmark
      }
      return { ...prev, [chunkId]: { lineIdx, firstType: "TEMAT", secondType: "TEMAT" } };
    });
  };

  const cancelLineSplit = (chunkId: number) => {
    setLineSplitStates(prev => { const n = { ...prev }; delete n[chunkId]; return n; });
  };

  const confirmLineSplit = async (chunkId: number) => {
    const st = lineSplitStates[chunkId];
    if (!st) return;
    setConfirmingLineSplit(prev => ({ ...prev, [chunkId]: true }));
    try {
      const r = await fetch(`${apiUrl}/chunk/${chunkId}/execute_split`, {
        method: "POST", headers,
        body: JSON.stringify({
          split_at_line: st.lineIdx,
          split_first_type: st.firstType,
          split_second_type: st.secondType,
        }),
      });
      const data = await r.json();
      if (data.status === "success") {
        cancelLineSplit(chunkId);
        if (selectedRun !== null) await fetchChunks(selectedRun);
      } else { setError("Błąd podziału: " + (data.message ?? "")); }
    } catch { setError("Błąd połączenia przy podziale"); }
    finally { setConfirmingLineSplit(prev => ({ ...prev, [chunkId]: false })); }
  };

  const mergeWithNext = async (chunk: Chunk) => {
    if (!window.confirm(`Scalić chunk #${chunk.position} z #${chunk.position + 1}? Scalony chunk będzie wymagał ponownej analizy.`)) return;
    try {
      const r = await fetch(`${apiUrl}/chunk/${chunk.id}/merge_with_next`, { method: "POST", headers });
      const data = await r.json();
      if (data.status === "success") {
        if (selectedRun !== null) await fetchChunks(selectedRun);
      } else { setError("Błąd scalania: " + (data.message ?? "")); }
    } catch { setError("Błąd połączenia przy scalaniu"); }
  };

  const deleteRun = async () => {
    if (selectedRun === null) return;
    if (!window.confirm(
      `Usunąć run #${selectedRun} wraz ze wszystkimi chunkami i sekcjami?\n`
      + "Powiązania chunków z notatkami Obsidian z tego runu zostaną utracone "
      + "(ścieżki na dokumencie pozostają)."
    )) return;
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}`, { method: "DELETE", headers });
      const data = await r.json();
      if (data.status === "success") {
        setInfo(`Run #${data.deleted_run_id} usunięty (${data.chunk_count} chunków)`);
        setChunks([]);
        setSelectedRun(null);
        setRuns([]);
        await fetchRuns();
      } else { setError("Błąd usuwania runa: " + (data.message ?? "")); }
    } catch { setError("Błąd połączenia przy usuwaniu runa"); }
  };

  const applyCleanupAndResplit = async () => {
    if (selectedRun === null || applyingCleanup || jobId) return;
    if (!window.confirm(
      "Nadpisać tekst źródłowy dokumentu treścią chunków TEMAT (REKLAMA/SZUM i usunięte linie znikną),\n"
      + "a następnie zaproponować NOWY PODZIAŁ (bez analizy LLM)?\n"
      + "Analizę uruchomisz przyciskiem 'Analizuj chunki' po przejrzeniu podziału."
    )) return;
    setApplyingCleanup(true);
    setError("");
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/apply_cleanup`, { method: "POST", headers });
      const data = await r.json();
      if (data.status !== "success") {
        setError("Błąd czyszczenia dokumentu: " + (data.message ?? ""));
        return;
      }
      setInfo(`Dokument wyczyszczony (${data.field}: ${data.length_before} → ${data.length_after} znaków, `
        + `odrzucono ${data.dropped_chunks} chunków). Startuję nowy podział (bez analizy LLM)…`);
      setPreviewNonce(n => n + 1);
      await startAnalysis("article", true);
    } catch { setError("Błąd połączenia przy czyszczeniu dokumentu"); }
    finally { setApplyingCleanup(false); }
  };

  // ── Split ──

  const markSplit = (chunkId: number, absIdx: number, ts: string) => {
    setSplitStates(prev => ({
      ...prev,
      [chunkId]: { segIdx: absIdx, ts, firstType: "REKLAMA", secondType: "TEMAT" },
    }));
  };

  const cancelSplit = (chunkId: number) => {
    setSplitStates(prev => { const n = { ...prev }; delete n[chunkId]; return n; });
  };

  const confirmSplit = async (chunkId: number) => {
    const st = splitStates[chunkId];
    if (!st) return;
    setConfirmingSplit(prev => ({ ...prev, [chunkId]: true }));
    try {
      const r = await fetch(`${apiUrl}/chunk/${chunkId}/execute_split`, {
        method: "POST", headers,
        body: JSON.stringify({ split_at_seg: st.segIdx, split_first_type: st.firstType, split_second_type: st.secondType }),
      });
      const data = await r.json();
      if (data.status === "success") {
        setSplitStates(prev => { const n = { ...prev }; delete n[chunkId]; return n; });
        if (selectedRun !== null) await fetchChunks(selectedRun);
      } else { setError("Błąd podziału: " + (data.message ?? "")); }
    } catch { setError("Błąd połączenia przy podziale"); }
    finally { setConfirmingSplit(prev => ({ ...prev, [chunkId]: false })); }
  };

  // ── Speakers ──

  const extractSpeakers = async () => {
    if (!selectedRun) return;
    setExtractingSpeakers(true);
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/extract_speakers`, { method: "POST", headers });
      const data = await r.json();
      if (data.status === "success") setSpeakers(data.speakers ?? []);
      else setError("Błąd wykrywania rozmówców");
    } catch { setError("Błąd połączenia przy wykrywaniu rozmówców"); }
    finally { setExtractingSpeakers(false); }
  };

  // ── Progress ──

  const tematChunks = chunks.filter(c => c.type === "TEMAT");
  const approvedCount = tematChunks.filter(c => c.status === "approved").length;
  const unapprovedTematCount = tematChunks.filter(c => c.status !== "approved").length;
  const pct = tematChunks.length ? Math.round(approvedCount / tematChunks.length * 100) : 0;
  const reklamaCount = chunks.filter(c => c.type !== "TEMAT").length;
  const visibleReklamaCount = chunks.filter(c => c.type !== "TEMAT" && !hiddenChunks.has(c.id)).length;
  const maxPosition = chunks.reduce((m, c) => Math.max(m, c.position), 0);
  const visibleChunks = chunks.filter(c =>
    !hiddenChunks.has(c.id) && (!hideAds || c.type === "TEMAT")
  );

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 6, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Przegląd chunków — dokument #{id}</h2>
        <NavLink to={`/${docType || "youtube"}/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>← Edytuj dokument</NavLink>
      </div>

      {/* Nowa analiza */}
      <div style={{ margin: "16px 0", padding: "12px 16px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
        <strong style={{ fontSize: "0.9em" }}>Nowa analiza</strong>
        <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select value={newModel} onChange={e => setNewModel(e.target.value)} style={{ padding: "4px 8px", fontSize: "0.88em" }}>
            {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={newMode} onChange={e => setNewMode(e.target.value)} style={{ padding: "4px 8px", fontSize: "0.88em" }}
            title="transkrypcja: mówcy + korekta STT; artykuł: czysty tekst, podział po nagłówkach, bez korekty">
            <option value="transcript">transkrypcja (YouTube)</option>
            <option value="article">artykuł (czysty tekst)</option>
          </select>
          <label style={{ fontSize: "0.85em" }}>
            Chunk:&nbsp;
            <input type="number" value={chunkSize} onChange={e => setChunkSize(Number(e.target.value))}
              style={{ width: 75, padding: "3px 6px", fontSize: "0.88em" }} min={500} max={20000} step={500} />
          </label>
          <label style={{ fontSize: "0.85em", display: "flex", alignItems: "center", gap: 4 }}
            title="Podziel na chunki bez wywołań LLM — najpierw doczyścisz/scalisz chunki, potem klikniesz Analizuj">
            <input type="checkbox" checked={splitOnly} onChange={e => setSplitOnly(e.target.checked)} />
            tylko podział (bez analizy LLM)
          </label>
          {splitPreview && (
            <span style={{ fontSize: "0.82em", color: "#475569" }}
              title={`Rozmiary chunków: ${splitPreview.sizes.join(", ")} znaków`}>
              → podział da <strong>{splitPreview.count}</strong> {splitPreview.count === 1 ? "chunk" : "chunki(-ów)"}
              {" "}({splitPreview.length.toLocaleString("pl")} zn
              {splitPreview.count > 1 && `: ${splitPreview.sizes.slice(0, 6).join(" + ")}${splitPreview.sizes.length > 6 ? " + …" : ""}`})
            </span>
          )}
          <button className="button" onClick={() => startAnalysis()} disabled={!!jobId}>
            {jobId ? `Analiza… (${jobStatus})` : "Uruchom analizę"}
          </button>
        </div>
      </div>

      {/* Wybór runu */}
      {runs.length > 0 && (
        <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
          <label style={{ fontSize: "0.85em", fontWeight: 600 }}>Analiza: </label>
          <select value={selectedRun ?? ""} onChange={e => setSelectedRun(Number(e.target.value))} style={{ padding: "4px 8px", fontSize: "0.88em" }}>
            {runs.map(r => (
              <option key={r.id} value={r.id}>
                #{r.id} — {r.model} ({r.chunk_count} chunków, {new Date(r.created_at).toLocaleString("pl")})
                {" "}[{r.mode === "article" ? "artykuł" : "transkrypcja"}
                {r.scope ? `, ${r.scope}` : ""}, {RUN_STATUS_LABELS[r.status] ?? r.status}]
              </option>
            ))}
          </select>
          <button onClick={deleteRun} title="Usuń wybrany run (chunki i sekcje)"
            style={{ padding: "3px 9px", border: "1px solid #fca5a5", borderRadius: 4, background: "#fff", color: "#b91c1c", cursor: "pointer", fontSize: "0.82em" }}>
            🗑 Usuń run
          </button>
        </div>
      )}

      {/* Pasek postępu */}
      {chunks.length > 0 && (
        <div style={{ marginBottom: 12, padding: "8px 14px", background: "#0f172a", borderRadius: 6, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ color: "#94a3b8", fontSize: "0.82em" }}>
            TEMAT: {approvedCount}/{tematChunks.length} zatwierdzonych ({pct}%)
            {reklamaCount > 0 && ` • ${reklamaCount} reklam/szum${hideAds ? " (ukryte)" : ""}`}
          </span>
          <div style={{ flex: 1, minWidth: 80, background: "#334155", borderRadius: 4, height: 8 }}>
            <div style={{ width: `${pct}%`, height: 8, background: "#22c55e", borderRadius: 4, transition: "width .3s" }} />
          </div>
          {unapprovedTematCount > 0 && (
            <button className="button" onClick={approveAll} disabled={approvingAll}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#15803d", color: "#fff", border: "none" }}>
              {approvingAll ? "Zatwierdzam…" : `Zatwierdź wszystkie (${unapprovedTematCount})`}
            </button>
          )}
          {chunksToAnalyze.length > 0 && (
            <button className="button" onClick={reanalyzeAll} disabled={reanalyzingAll}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#0369a1", color: "#fff", border: "none" }}>
              {reanalyzingAll ? "Analizuję…" : `Analizuj chunki (${chunksToAnalyze.length})`}
            </button>
          )}
          {reklamaCount > 0 && (visibleReklamaCount > 0 || hideAds) && (
            <button className="button" onClick={() => setHideAds(h => !h)}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: hideAds ? "#475569" : "#b91c1c", color: "#fff", border: "none" }}>
              {hideAds ? `Pokaż reklamy i szum (${reklamaCount})` : `Ukryj reklamy i szum (${visibleReklamaCount})`}
            </button>
          )}
          {hiddenChunks.size > 0 && (
            <button className="button" onClick={() => setHiddenChunks(new Set())}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#0369a1", color: "#fff", border: "none" }}>
              Pokaż ukryte ({hiddenChunks.size})
            </button>
          )}
        </div>
      )}

      {/* Pasek rozmówców (tylko transkrypcje — artykuły nie mają mówców) */}
      {selectedRun !== null && runMode !== "article" && (
        <div style={{ marginBottom: 12, padding: "8px 14px", background: "#1e3a5f", borderRadius: 6, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <strong style={{ color: "#fff", fontSize: "0.85em" }}>Rozmówcy:</strong>
          {speakers.length > 0 ? (
            <span style={{ fontSize: "0.85em" }}>
              {speakers.map((sp, i) => (
                <React.Fragment key={i}>
                  {i > 0 && <span style={{ color: "#64748b" }}> &nbsp;|&nbsp; </span>}
                  <strong style={{ color: "#fff" }}>{sp.name}</strong>
                  {sp.role && <span style={{ color: "#93c5fd" }}> ({sp.role})</span>}
                </React.Fragment>
              ))}
            </span>
          ) : (
            <span style={{ color: "#64748b", fontSize: "0.85em", fontStyle: "italic" }}>nie wykryto</span>
          )}
          <button className="button" onClick={extractSpeakers} disabled={extractingSpeakers}
            style={{ marginLeft: "auto", fontSize: "0.82em", padding: "3px 10px" }}>
            {extractingSpeakers ? "Wykrywam…" : speakers.length > 0 ? `Wykryj ponownie (${speakers.length})` : "Wykryj rozmówców"}
          </button>
        </div>
      )}

      {error && <p style={{ color: "#dc2626", marginBottom: 12 }}>{error}</p>}
      {info && <p style={{ color: "#15803d", marginBottom: 12 }}>{info}</p>}
      {loading && <div className="loader" style={{ marginBottom: 12 }} />}

      {/* Czyszczenie dokumentu z runa artykułowego */}
      {runMode === "article" && chunks.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <button className="button" onClick={applyCleanupAndResplit} disabled={applyingCleanup || !!jobId}
            title="Nadpisuje tekst źródłowy dokumentu treścią chunków TEMAT (REKLAMA/SZUM i usunięte linie znikają), po czym uruchamia nową analizę"
            style={{ fontSize: "0.85em", background: "#7c3aed", color: "#fff", border: "none", padding: "4px 12px" }}>
            {applyingCleanup ? "Czyszczę dokument…" : "Wyczyść dokument i zaproponuj nowy podział"}
          </button>
        </div>
      )}

      {/* Chunki */}
      {visibleChunks.map((chunk, i) => {
        const hasCorrected = !!chunk.corrected_text;
        const isCorrectedView = showCorrected[chunk.id] ?? hasCorrected;
        const isReanalyzing = reanalyzing[chunk.id] ?? false;
        const splitSt = splitStates[chunk.id];
        const lineSplitSt = lineSplitStates[chunk.id];
        const chunkSegs = segments.slice(chunk.seg_start ?? 0, chunk.seg_end ?? segments.length);

        return (
          <div key={chunk.id} style={{ marginBottom: 18, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>

            {/* Nagłówek */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "#f1f5f9", borderBottom: "1px solid #e2e8f0", fontSize: "0.82em", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 600, color: "#334155", minWidth: 24 }}>#{chunk.position}</span>

              {/* Typ — klikalny */}
              <span
                onClick={() => toggleType(chunk)}
                title="Kliknij aby zmienić typ"
                style={{
                  cursor: "pointer", padding: "1px 8px", borderRadius: 4, fontWeight: 600,
                  ...typeColor(chunk.type),
                }}
              >
                {chunk.type ?? "?"}
              </span>

              {/* Status — klikalny */}
              <span
                onClick={() => cycleStatus(chunk)}
                title="Kliknij aby zmienić status"
                style={{ cursor: "pointer", padding: "1px 8px", borderRadius: 4, fontWeight: 500, ...statusColor(chunk.status) }}
              >
                {chunk.status}
              </span>

              {chunk.speaker && <span style={{ color: "#64748b" }}>🎙 {chunk.speaker}</span>}

              {/* Edycja tematu */}
              <input
                type="text"
                value={topicEdits[chunk.id] ?? ""}
                onChange={e => setTopicEdits(prev => ({ ...prev, [chunk.id]: e.target.value }))}
                onKeyDown={e => { if (e.key === "Enter") saveTopic(chunk.id); }}
                placeholder="temat"
                style={{ flex: 1, minWidth: 100, border: "none", borderBottom: "1px dashed #cbd5e1", background: "transparent", fontSize: "0.88em", padding: "2px 4px", color: "#334155" }}
              />
              <button onClick={() => saveTopic(chunk.id)} disabled={savingTopics[chunk.id]}
                style={{ padding: "2px 10px", borderRadius: 3, border: "none", background: "#3b82f6", color: "#fff", fontSize: "0.78em", cursor: "pointer", fontWeight: "bold" }}>
                Zapisz
              </button>
              {savedFlash[chunk.id] && <span style={{ color: "#15803d", fontSize: "0.78em" }}>✓</span>}

              {/* Re-analiza */}
              <button onClick={() => reanalyzeChunk(chunk.id, "full")} disabled={isReanalyzing}
                style={{ padding: "2px 9px", borderRadius: 3, border: "none", background: "#7c3aed", color: "#fff", fontSize: "0.78em", cursor: "pointer", fontWeight: "bold" }}>
                {isReanalyzing ? "…" : "▶ Pełna"}
              </button>
              {hasCorrected && (
                <button onClick={() => reanalyzeChunk(chunk.id, "semantic")} disabled={isReanalyzing}
                  style={{ padding: "2px 9px", borderRadius: 3, border: "none", background: "#059669", color: "#fff", fontSize: "0.78em", cursor: "pointer", fontWeight: "bold" }}>
                  {isReanalyzing ? "…" : "▶ Sem."}
                </button>
              )}

              {/* Przełącznik widoku */}
              {hasCorrected && (
                <button onClick={() => setShowCorrected(prev => ({ ...prev, [chunk.id]: !prev[chunk.id] }))}
                  style={{ padding: "2px 9px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em" }}>
                  {isCorrectedView ? "Surowy" : "Poprawiony"}
                </button>
              )}
              {chunk.position < maxPosition && (
                <button
                  onClick={() => mergeWithNext(chunk)}
                  title={`Scal z chunkiem #${chunk.position + 1}`}
                  style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em", color: "#64748b" }}
                >
                  ⇣ Scal
                </button>
              )}
              <button
                onClick={() => setHiddenChunks(prev => new Set([...prev, chunk.id]))}
                title="Ukryj ten chunk"
                style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em", color: "#64748b", marginLeft: "auto" }}
              >
                ✕
              </button>
            </div>

            {/* Treść: poprawiony tekst → segmenty transkrypcji → surowy tekst (artykuły) */}
            <div style={{ padding: "12px 14px", fontSize: "0.88em", lineHeight: 1.6 }}>
              {isCorrectedView && hasCorrected ? (
                <div style={{ whiteSpace: "pre-wrap", color: "#1e293b" }}>{chunk.corrected_text}</div>
              ) : chunkSegs.length > 0 ? (
                <SegmentsView
                  segs={chunkSegs}
                  videoId={videoId}
                  chunkId={chunk.id}
                  absOffset={chunk.seg_start ?? 0}
                  splitState={splitSt}
                  onMarkSplit={markSplit}
                />
              ) : (
                <PlainTextLines
                  text={chunk.original_text ?? ""}
                  markedLines={lineEdits[chunk.id] ?? new Set()}
                  splitLineIdx={lineSplitStates[chunk.id]?.lineIdx ?? null}
                  saving={savingLines[chunk.id] ?? false}
                  onToggleLine={idx => toggleLineMark(chunk.id, idx)}
                  onMarkSplit={idx => markLineSplit(chunk.id, idx)}
                  onSave={removeFromDoc => saveLineRemovals(chunk, removeFromDoc)}
                  onCancel={() => clearLineMarks(chunk.id)}
                />
              )}
            </div>

            {/* Panel podziału */}
            {splitSt && (
              <div style={{ margin: "0 14px 14px", padding: "10px 12px", background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 5, fontSize: "0.84em" }}>
                <strong style={{ color: "#92400e" }}>✂ Punkt podziału: [{splitSt.ts}]</strong>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
                  <label>Część 1 (przed):&nbsp;
                    <select value={splitSt.firstType}
                      onChange={e => setSplitStates(prev => ({ ...prev, [chunk.id]: { ...prev[chunk.id], firstType: e.target.value as ChunkType } }))}
                      style={{ padding: "2px 6px", borderRadius: 3 }}>
                      <option value="REKLAMA">REKLAMA</option>
                      <option value="TEMAT">TEMAT</option>
                      <option value="SZUM">SZUM</option>
                    </select>
                  </label>
                  <label>Część 2 (po):&nbsp;
                    <select value={splitSt.secondType}
                      onChange={e => setSplitStates(prev => ({ ...prev, [chunk.id]: { ...prev[chunk.id], secondType: e.target.value as ChunkType } }))}
                      style={{ padding: "2px 6px", borderRadius: 3 }}>
                      <option value="TEMAT">TEMAT</option>
                      <option value="REKLAMA">REKLAMA</option>
                      <option value="SZUM">SZUM</option>
                    </select>
                  </label>
                  <button onClick={() => confirmSplit(chunk.id)} disabled={confirmingSplit[chunk.id]}
                    style={{ padding: "3px 12px", background: "#f97316", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer", fontWeight: "bold", fontSize: "0.82em" }}>
                    {confirmingSplit[chunk.id] ? "Dzielę…" : "Wykonaj podział"}
                  </button>
                  <button onClick={() => cancelSplit(chunk.id)}
                    style={{ padding: "3px 10px", background: "#e2e8f0", color: "#475569", border: "none", borderRadius: 3, cursor: "pointer", fontSize: "0.82em" }}>
                    Anuluj
                  </button>
                </div>
                <div style={{ color: "#92400e", fontSize: "0.8em", marginTop: 4 }}>Kliknij ✂ przy innym akapicie aby zmienić punkt podziału.</div>
              </div>
            )}

            {/* Panel podziału liniowego (chunki artykułowe) */}
            {lineSplitSt && (
              <div style={{ margin: "0 14px 14px", padding: "10px 12px", background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 5, fontSize: "0.84em" }}>
                <strong style={{ color: "#92400e" }}>✂ Punkt podziału: linia {lineSplitSt.lineIdx + 1} (zaczyna nowy chunk)</strong>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
                  <label>Część 1 (przed):&nbsp;
                    <select value={lineSplitSt.firstType}
                      onChange={e => setLineSplitStates(prev => ({ ...prev, [chunk.id]: { ...prev[chunk.id], firstType: e.target.value as ChunkType } }))}
                      style={{ padding: "2px 6px", borderRadius: 3 }}>
                      <option value="TEMAT">TEMAT</option>
                      <option value="REKLAMA">REKLAMA</option>
                      <option value="SZUM">SZUM</option>
                    </select>
                  </label>
                  <label>Część 2 (po):&nbsp;
                    <select value={lineSplitSt.secondType}
                      onChange={e => setLineSplitStates(prev => ({ ...prev, [chunk.id]: { ...prev[chunk.id], secondType: e.target.value as ChunkType } }))}
                      style={{ padding: "2px 6px", borderRadius: 3 }}>
                      <option value="TEMAT">TEMAT</option>
                      <option value="REKLAMA">REKLAMA</option>
                      <option value="SZUM">SZUM</option>
                    </select>
                  </label>
                  <button onClick={() => confirmLineSplit(chunk.id)} disabled={confirmingLineSplit[chunk.id]}
                    style={{ padding: "3px 12px", background: "#f97316", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer", fontWeight: "bold", fontSize: "0.82em" }}>
                    {confirmingLineSplit[chunk.id] ? "Dzielę…" : "Wykonaj podział"}
                  </button>
                  <button onClick={() => cancelLineSplit(chunk.id)}
                    style={{ padding: "3px 10px", background: "#e2e8f0", color: "#475569", border: "none", borderRadius: 3, cursor: "pointer", fontSize: "0.82em" }}>
                    Anuluj
                  </button>
                </div>
                <div style={{ color: "#92400e", fontSize: "0.8em", marginTop: 4 }}>Kliknij ✂ przy innej linii aby zmienić punkt podziału. Części TEMAT dostaną status needs_reanalysis.</div>
              </div>
            )}

            {/* Podsumowanie */}
            {chunk.summary && (
              <div style={{ padding: "10px 14px", background: "#f8fafc", borderTop: "1px solid #e2e8f0", fontSize: "0.85em", color: "#475569" }}>
                <div style={{ fontWeight: 600, color: "#64748b", fontSize: "0.8em", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>Podsumowanie</div>
                <p style={{ margin: 0, lineHeight: 1.5 }}>{chunk.summary}</p>
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
