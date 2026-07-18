import React from "react";
import { useParams, useLocation, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import {
  NotePopover, NoteRow, PendingNote, ReaderIdentityBadge, STANCE_ICON, UserNote,
  normalizeWs, pendingNoteFromSelection, useReaderIdentity, useUserNotes,
} from "../components/ReaderNotes/readerNotes";
import { buildObsidianNoteUrl } from "../utils/obsidian";

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
  obsidian_note_paths?: string[];
  has_embeddings?: boolean | null;
  photo_caption_line_indices?: number[];
  cited_publications?: CitedPublicationSummary[];
  // lite responses (big runs): texts stripped, preview + length instead
  text_length?: number | null;
  text_preview?: string | null;
}

interface CitedPublicationSummary {
  id: number;
  publication_id: number;
  title: string | null;
  pmid: string | null;
  pmcid: string | null;
  doi: string | null;
  canonical_url: string;
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
  temat_count?: number;
  approved_count?: number;
  workflow_stage?: "split_proposal" | "cleanup_proposal" | "analysis" | "reviewed" | "superseded";
}

interface TopicSection {
  id: number;
  position: number;
  type: string;
  title: string | null;
  summary: string | null;
  chunk_positions: number[];
  chunk_count: number;
  temat_count: number;
  approved_count: number;
  notes_count: number;
}

interface Chapter {
  position: number;
  level: number;
  title: string;
  char_start: number;
  char_end: number;
  length: number;
}

interface SiteRulesFileStatus {
  ok: boolean;
  path: string;
  reason: "missing" | "empty_or_invalid" | null;
}

interface RecleanPreview {
  source_field: string;
  portal: string | null;
  site_rules_file: SiteRulesFileStatus;
  before_length: number;
  after_length: number;
  before_line_count: number;
  after_line_count: number;
  removed_line_count: number;
  removed_lines_preview: string[];
  before_start_preview: string;
  before_end_preview: string;
  start_preview: string;
  end_preview: string;
  saved: boolean;
}

interface CountryTag {
  slug: string;
  name_pl: string;
}

interface AuthorPerson {
  person_id: number;
  link_id: number;
  name: string;
  description: string | null;
  confidence: string;
  wikidata_qid: string | null;
}

interface DocQuality {
  score: number;
  penalties: Record<string, number>;
  signals?: {
    photo_captions?: number;
    photo_caption_categories?: Record<string, number>;
    photo_source_penalty_details?: Record<string, number>;
    noise_share?: number;
    temat_chars?: number;
  };
  llm_rubric?: { zrodla: number; glebia: number; jezyk: number; uzasadnienie?: string } | null;
}

const QUALITY_PENALTY_LABELS: Record<string, string> = {
  photo_captions: "podpisy zdjęć",
  photo_sources: "pochodzenie zdjęć",
  missing_author: "brak autora",
  noise_share: "udział reklam/szumu",
  short_text: "bardzo krótki tekst",
  clickbait_title: "clickbaitowy tytuł",
  llm_rubric: "rubryka LLM (źródła/głębia/język)",
};

function qualityTooltip(q: DocQuality): string {
  const lines = Object.entries(q.penalties ?? {}).map(
    ([key, pts]) => `−${pts}: ${QUALITY_PENALTY_LABELS[key] ?? key}`,
  );
  if (lines.length === 0) lines.push("bez zastrzeżeń");
  const photoCategories = q.signals?.photo_caption_categories;
  if (photoCategories && Object.keys(photoCategories).length > 0) {
    const labels: Record<string, string> = {
      own_or_private_archive: "własne/prywatne archiwum",
      agency: "agencyjne",
      creative_commons: "Creative Commons",
      public_domain: "domena publiczna",
      stock: "stockowe",
      illustrative: "ilustracyjne",
      image_credit: "inne podpisane",
      other: "inne źródła",
    };
    lines.push(`Zdjęcia: ${Object.entries(photoCategories)
      .map(([key, count]) => `${labels[key] ?? key}: ${count}`)
      .join(", ")}`);
  }
  if (q.llm_rubric) {
    lines.push(`LLM — źródła: ${q.llm_rubric.zrodla}/5, głębia: ${q.llm_rubric.glebia}/5, język: ${q.llm_rubric.jezyk}/5`);
    if (q.llm_rubric.uzasadnienie) lines.push(q.llm_rubric.uzasadnienie);
  }
  return lines.join("\n");
}

function qualityColors(score: number): React.CSSProperties {
  if (score >= 75) return { background: "#dcfce7", color: "#15803d" };
  if (score >= 50) return { background: "#fef3c7", color: "#b45309" };
  return { background: "#fee2e2", color: "#b91c1c" };
}

const RUN_STATUS_LABELS: Record<string, string> = {
  created: "nowa",
  in_review: "w przeglądzie",
  reviewed: "zamknięta",
  superseded: "zastąpiona nowszą",
};

function runLabelText(r: AnalysisRun): string {
  const parts = [r.mode === "article" ? "artykuł" : "transkrypcja"];
  if (r.scope) parts.push(r.scope);
  if (r.temat_count != null && r.temat_count > 0) parts.push(`✓ ${r.approved_count}/${r.temat_count}`);
  if (r.workflow_stage === "cleanup_proposal") parts.push("propozycja czyszczenia");
  if (r.workflow_stage === "split_proposal") parts.push("propozycja podziału");
  parts.push(RUN_STATUS_LABELS[r.status] ?? r.status);
  return `#${r.id} — ${r.model} (${r.chunk_count} chunków, ${new Date(r.created_at).toLocaleString("pl")}) [${parts.join(", ")}]`;
}

type ChunkType = "TEMAT" | "ZRODLA" | "REKLAMA" | "SZUM";

interface SplitState {
  segIdx: number;
  ts: string;
  firstType: ChunkType;
  secondType: ChunkType;
}

interface LineSplitState {
  lineIndices: Set<number>;
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
const TYPE_CYCLE: ChunkType[] = ["TEMAT", "SZUM", "ZRODLA", "REKLAMA"];

// Speaker self-introductions are expected near the start of a transcript, so the
// per-chunk "detect speakers from just this chunk" button only appears on the
// first few chunks — matches the backend default (first 3 chunks) with some
// slack for reviewers who split the intro out into a later position.
const SPEAKER_DETECT_CHUNK_LIMIT = 5;

// Runs bigger than this are fetched lite (no chunk texts) and browsed through
// the section accordion (books); flat runs without sections get paged instead.
const SECTION_VIEW_THRESHOLD = 30;
const CHUNK_PAGE_SIZE = 20;

// Document types with an editor route in App.tsx. Types without one
// (text, text_message, social_media_post) get a back-link to /list instead.
const EDITOR_TYPES = ["webpage", "link", "youtube", "movie", "email"];

const DOC_TYPE_LABELS: Record<string, string> = {
  webpage: "artykuł",
  link: "link",
  youtube: "YouTube",
  movie: "film",
  email: "e-mail",
  text: "tekst",
  text_message: "wiadomość",
  social_media_post: "post społecznościowy",
};

function typeColor(type: string | null): React.CSSProperties {
  switch (type) {
    case "ZRODLA":  return { background: "#ede9fe", color: "#6d28d9" };
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
  photoCaptionLines: Set<number>;
  splitLineIndices: Set<number>;
  saving: boolean;
  detectingAuthorLine: number | null;
  onToggleLine: (idx: number) => void;
  onTogglePhotoBlock: (indices: number[]) => void;
  onMarkSplit: (idx: number) => void;
  onDetectAuthor: (idx: number) => void;
  onReplaceText: (text: string) => Promise<boolean>;
  onSave: (removeFromDocument: boolean) => void;
  onCancel: () => void;
}> = ({ text, markedLines, photoCaptionLines, splitLineIndices, saving, detectingAuthorLine, onToggleLine, onTogglePhotoBlock, onMarkSplit, onDetectAuthor, onReplaceText, onSave, onCancel }) => {
  const [removeFromDoc, setRemoveFromDoc] = React.useState(true);
  const [editingText, setEditingText] = React.useState(false);
  const [draftText, setDraftText] = React.useState(text);
  React.useEffect(() => { if (!editingText) setDraftText(text); }, [text, editingText]);
  if (!text) return <em style={{ color: "#94a3b8" }}>brak tekstu</em>;
  const lines = text.split("\n");
  const lineBtnStyle: React.CSSProperties = {
    background: "none", border: "1px solid #e2e8f0", borderRadius: 3,
    fontSize: "0.78em", cursor: "pointer", padding: "0 4px", lineHeight: "1.3em",
  };
  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <button type="button" onClick={() => { setDraftText(text); setEditingText(value => !value); }}
          style={{ padding: "2px 9px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em", color: "#475569" }}>
          {editingText ? "Anuluj edycję" : "✎ Edytuj linie"}
        </button>
      </div>
      {editingText ? (
        <div style={{ marginBottom: 10 }}>
          <textarea value={draftText} onChange={e => setDraftText(e.target.value)} autoFocus
            title="Enter tworzy nową linię; każda linia po zapisie dostanie osobne przyciski ×, ✂ i A"
            style={{ width: "100%", minHeight: 180, boxSizing: "border-box", padding: 8, fontFamily: "inherit", fontSize: "1em", lineHeight: 1.55 }} />
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
            <button type="button" disabled={saving || !draftText.trim()} onClick={async () => {
              if (await onReplaceText(draftText)) setEditingText(false);
            }} style={{ padding: "3px 12px", background: "#0369a1", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer", fontWeight: 600 }}>
              {saving ? "Zapisuję…" : "Zapisz nowe linie"}
            </button>
            <span style={{ color: "#64748b", fontSize: "0.8em" }}>Enter dodaje linię. Po zapisie możesz użyć ✂ przy kilku liniach.</span>
          </div>
        </div>
      ) : <>
      {lines.map((line, i) => {
        const marked = markedLines.has(i);
        const isPhotoCaption = photoCaptionLines.has(i);
        const isSplitMark = splitLineIndices.has(i);
        const photoBlockIndices = (() => {
          if (!isPhotoCaption || i + 2 >= lines.length || lines[i + 1].trim()) return [];
          let descriptionIndex = i + 1;
          while (descriptionIndex < lines.length && !lines[descriptionIndex].trim()) descriptionIndex += 1;
          if (descriptionIndex >= lines.length || lines[descriptionIndex].trim().startsWith("#") || lines[descriptionIndex].trim().length > 300) return [];
          return Array.from({ length: descriptionIndex - i + 1 }, (_, offset) => i + offset);
        })();
        const photoBlockMarked = photoBlockIndices.length > 0 && photoBlockIndices.every(idx => markedLines.has(idx));
        return (
          <div
            key={i}
            style={{
              position: "relative", paddingLeft: photoBlockIndices.length > 0 ? 122 : 82, borderRadius: 2, minHeight: "1.4em",
              ...(marked ? { background: "#fee2e2", textDecoration: "line-through", color: "#991b1b" } : {}),
              ...(!marked && isPhotoCaption ? { background: "#fefce8", borderLeft: "3px solid #eab308" } : {}),
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
              <button
                onClick={() => onDetectAuthor(i)}
                disabled={detectingAuthorLine !== null}
                title="Wykryj autora z tej linii i sąsiednich zdań"
                style={{ ...lineBtnStyle, color: "#7c3aed", fontWeight: "bold" }}
              >
                {detectingAuthorLine === i ? "…" : "A"}
              </button>
              {photoBlockIndices.length > 0 && (
                <button
                  onClick={() => onTogglePhotoBlock(photoBlockIndices)}
                  title={photoBlockMarked ? "Przywróć źródło, odstęp i opis zdjęcia" : "Usuń źródło, odstęp i opis zdjęcia"}
                  style={{ ...lineBtnStyle, color: photoBlockMarked ? "#991b1b" : "#b45309", fontWeight: "bold" }}
                >
                  {photoBlockMarked ? "↶ blok" : "× blok"}
                </button>
              )}
            </span>
            <span style={{ whiteSpace: "pre-wrap" }}>{line || " "}</span>
            {isPhotoCaption && (
              <span
                title="Podpis lub credit zdjęcia: zachowany dla oceny jakości, pomijany przy generowaniu embeddingów"
                style={{ marginLeft: 8, padding: "1px 5px", borderRadius: 3, background: "#fef08a", color: "#854d0e", fontSize: "0.75em", whiteSpace: "nowrap" }}
              >
                📷 kandydat do usunięcia
              </span>
            )}
          </div>
        );
      })}
      </>}
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
  const [docTitle, setDocTitle]     = React.useState("");
  const [docAuthor, setDocAuthor]   = React.useState("");
  const [docAuthorSource, setDocAuthorSource] = React.useState<string | null>(null);
  const [authorPersons, setAuthorPersons] = React.useState<AuthorPerson[]>([]);
  const [authorInput, setAuthorInput] = React.useState("");
  const [savingAuthor, setSavingAuthor] = React.useState(false);
  const [docDateFrom, setDocDateFrom] = React.useState<string | null>(null);
  const [docDateFromSource, setDocDateFromSource] = React.useState<string | null>(null);
  const [extractingDateFor, setExtractingDateFor] = React.useState<number | null>(null);
  const [dateInput, setDateInput] = React.useState("");
  const [savingDate, setSavingDate] = React.useState(false);
  const [docUrl, setDocUrl]         = React.useState("");
  const [docQuality, setDocQuality] = React.useState<DocQuality | null>(null);
  const [computingQuality, setComputingQuality] = React.useState(false);
  const [refreshingCitationsFor, setRefreshingCitationsFor] = React.useState<number | null>(null);
  const [reportingIssue, setReportingIssue] = React.useState(false);
  const [runMode, setRunMode]       = React.useState("transcript");
  const [speakers, setSpeakers]     = React.useState<Speaker[]>([]);

  const [loading, setLoading]       = React.useState(false);
  const [error, setError]           = React.useState("");
  const [info, setInfo]             = React.useState("");
  const [applyingCleanup, setApplyingCleanup] = React.useState(false);
  const [jobStatus, setJobStatus]   = React.useState<string | null>(null);
  const [jobId, setJobId]           = React.useState<string | null>(null);
  const jobPollRef = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const [newModel, setNewModel]     = React.useState(MODELS[0]);
  const [newMode, setNewMode]       = React.useState("transcript");
  const [splitOnly, setSplitOnly]   = React.useState(false);
  const [preclean, setPreclean]     = React.useState(true);
  const [chunkSize, setChunkSize]   = React.useState(5000);
  const [splitPreview, setSplitPreview] = React.useState<{ count: number; sizes: number[]; length: number } | null>(null);
  const [previewNonce, setPreviewNonce] = React.useState(0);
  const [recleanPreview, setRecleanPreview] = React.useState<RecleanPreview | null>(null);
  const [useRecleaned, setUseRecleaned] = React.useState(false);
  const [recleaning, setRecleaning] = React.useState(false);
  const [hideAds, setHideAds]       = React.useState(false);

  const [showCorrected, setShowCorrected] = React.useState<Record<number, boolean>>({});
  const [topicEdits, setTopicEdits]       = React.useState<Record<number, string>>({});
  const [savingTopics, setSavingTopics]   = React.useState<Record<number, boolean>>({});
  const [savedFlash, setSavedFlash]       = React.useState<Record<number, boolean>>({});
  const [reanalyzing, setReanalyzing]     = React.useState<Record<number, boolean>>({});
  const [deletingChunks, setDeletingChunks] = React.useState<Record<number, boolean>>({});
  const [reanalyzingAll, setReanalyzingAll] = React.useState(false);
  const [approvingAll, setApprovingAll] = React.useState(false);
  const [splitStates, setSplitStates]     = React.useState<Record<number, SplitState>>({});
  const [lineEdits, setLineEdits]         = React.useState<Record<number, Set<number>>>({});
  const [savingLines, setSavingLines]     = React.useState<Record<number, boolean>>({});
  const [lineSplitStates, setLineSplitStates] = React.useState<Record<number, LineSplitState>>({});
  const [confirmingLineSplit, setConfirmingLineSplit] = React.useState<Record<number, boolean>>({});
  const [confirmingSplit, setConfirmingSplit] = React.useState<Record<number, boolean>>({});
  const [extractingSpeakers, setExtractingSpeakers] = React.useState(false);
  const [extractingSpeakerFor, setExtractingSpeakerFor] = React.useState<number | null>(null);
  const [extractingAuthorFor, setExtractingAuthorFor] = React.useState<number | null>(null);
  const [extractingAuthorLine, setExtractingAuthorLine] = React.useState<{ chunkId: number; lineIdx: number } | null>(null);
  const [runStatus, setRunStatus] = React.useState("created");
  const [synthesis, setSynthesis] = React.useState("");
  const [synthesisOpen, setSynthesisOpen] = React.useState(false);
  const [docCountries, setDocCountries] = React.useState<CountryTag[]>([]);
  const [docThematicTags, setDocThematicTags] = React.useState<string[]>([]);
  const [chapters, setChapters]   = React.useState<Chapter[]>([]);
  const [scopeChapter, setScopeChapter] = React.useState<number | "">("");
  const [topicSections, setTopicSections] = React.useState<TopicSection[]>([]);
  const [sectionView, setSectionView] = React.useState(false);
  const [expandedSections, setExpandedSections] = React.useState<Set<number>>(new Set());
  const [loadedSections, setLoadedSections] = React.useState<Set<number>>(new Set());
  const [loadingSections, setLoadingSections] = React.useState<Record<number, boolean>>({});
  const [sectionTitleEdits, setSectionTitleEdits] = React.useState<Record<number, string>>({});
  const [editingSectionId, setEditingSectionId] = React.useState<number | null>(null);
  const [savingSectionTitle, setSavingSectionTitle] = React.useState(false);
  const [flatPaged, setFlatPaged] = React.useState(false);
  const [chunkTotal, setChunkTotal] = React.useState(0);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [hiddenChunks, setHiddenChunks] = React.useState<Set<number>>(new Set());
  const [filterUnprocessed, setFilterUnprocessed] = React.useState(false);
  const [embedJobId, setEmbedJobId] = React.useState<string | null>(null);
  const [embedJobStatus, setEmbedJobStatus] = React.useState<string | null>(null);
  const [showCompletedResult, setShowCompletedResult] = React.useState(false);
  const [loadingNextDocument, setLoadingNextDocument] = React.useState(false);

  // ── User identity + fragment notes (shared with /read) ──
  const identity = useReaderIdentity(apiUrl, apiKey);
  const { userId } = identity;
  const { notes, createNote, saveNoteText, deleteNote } = useUserNotes(apiUrl, id, identity);
  const [pendingNote, setPendingNote] = React.useState<(PendingNote & { chunkId: number }) | null>(null);
  const [expandedNoteChunks, setExpandedNoteChunks] = React.useState<Set<number>>(new Set());

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
    // Big runs (books): fetch lite (no chunk texts) and browse via sections
    const big = (runs.find(r => r.id === runId)?.chunk_count ?? 0) > SECTION_VIEW_THRESHOLD;
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${runId}/chunks${big ? "?lite=1" : ""}`, { headers });
      const data = await r.json();
      let loaded: Chunk[] = data.chunks ?? [];
      const sections: TopicSection[] = data.topic_sections ?? [];
      const useSections = big && sections.length > 0;
      let paged = false;
      if (big && sections.length === 0) {
        // No sections to group by (e.g. split_only) — page the flat list
        const r2 = await fetch(
          `${apiUrl}/analysis_run/${runId}/chunks?offset=0&limit=${CHUNK_PAGE_SIZE}`, { headers });
        const d2 = await r2.json();
        loaded = d2.chunks ?? [];
        paged = true;
      }
      setChunks(loaded);
      setTopicSections(sections);
      setSectionView(useSections);
      setExpandedSections(new Set());
      setLoadedSections(new Set());
      setEditingSectionId(null);
      setFlatPaged(paged);
      setChunkTotal(data.chunk_total ?? loaded.length);
      setSegments(data.segments ?? []);
      setVideoId(data.document?.original_id ?? "");
      setDocType(data.document?.document_type ?? "");
      setDocUrl(data.document?.url ?? "");
      setDocAuthor(data.document?.author ?? "");
      setDocAuthorSource(data.document?.author_source ?? null);
      setAuthorPersons(data.document?.author_persons ?? []);
      setAuthorInput(data.document?.author ?? "");
      setDocDateFrom(data.document?.date_from ?? null);
      setDocDateFromSource(data.document?.date_from_source ?? null);
      setDateInput(data.document?.date_from ?? "");
      setDocQuality(data.document?.quality ?? null);
      setDocCountries(data.document?.countries ?? []);
      setDocThematicTags(data.document?.thematic_tags ?? []);
      setRunMode(data.run?.mode ?? "transcript");
      setRunStatus(data.run?.status ?? "created");
      setSpeakers(data.run?.speakers ?? []);
      setSynthesis(data.run?.synthesis ?? "");
      setSynthesisOpen(false);
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
      setShowCompletedResult(false);
    } catch {
      setError("Błąd ładowania chunków");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, apiKey, runs]);

  React.useEffect(() => { fetchRuns(); }, [fetchRuns]);
  React.useEffect(() => { if (selectedRun !== null) fetchChunks(selectedRun); }, [selectedRun, fetchChunks]);
  // Direct links to /chunks/:id do not carry router state. Load the document
  // type (so the basic flow can choose article/transcript without user input)
  // and title (so the page header shows what document this is, not just the id).
  React.useEffect(() => {
    if (!id || (docType && docTitle)) return;
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/website_get?id=${id}`, { headers: { "x-api-key": apiKey ?? "" } });
        const data = await r.json();
        if (data.document_type) setDocType(data.document_type);
        if (data.title) setDocTitle(data.title);
        if (data.url) setDocUrl(data.url);
        if (data.author) { setDocAuthor(data.author); setAuthorInput(data.author); }
        if (data.author_source) setDocAuthorSource(data.author_source);
        if (data.date_from) { setDocDateFrom(data.date_from); setDateInput(data.date_from); }
        if (data.quality) setDocQuality(data.quality);
      } catch { /* analysis can still be configured manually */ }
    })();
  }, [id, docType, docTitle, apiUrl, apiKey]);
  // Clean documents (articles, webpages) default to article mode for new analyses
  React.useEffect(() => {
    if (docType && docType !== "youtube" && docType !== "movie") setNewMode("article");
  }, [docType]);

  // Book support: detect the document's table of contents (H1/H2) for article mode
  React.useEffect(() => {
    if (!id || newMode !== "article") { setChapters([]); setScopeChapter(""); return; }
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/chapters`, { headers: { "x-api-key": apiKey ?? "" } });
        const data = await r.json();
        setChapters(data.status === "success" ? (data.chapters ?? []) : []);
      } catch { setChapters([]); }
    })();
  }, [id, newMode, apiUrl, apiKey]);

  // Live preview: how many chunks would a new split produce (no LLM, debounced)
  React.useEffect(() => {
    if (!id) return;
    const t = setTimeout(async () => {
      try {
        const scopeParam = newMode === "article" && scopeChapter !== "" ? `&scope_chapter=${scopeChapter}` : "";
        const recleanParam = newMode === "article" && useRecleaned ? "&reclean=1" : "";
        const r = await fetch(
          `${apiUrl}/document/${id}/split_preview?mode=${newMode}&chunk_size=${chunkSize}${scopeParam}${recleanParam}`,
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
  }, [id, newMode, chunkSize, scopeChapter, useRecleaned, apiUrl, apiKey, previewNonce]);

  // Before the first run, the user cannot know whether deterministic cleanup is
  // needed. Compare source and cleaner output automatically (read-only).
  React.useEffect(() => {
    if (!id || newMode !== "article") { setRecleanPreview(null); return; }
    const controller = new AbortController();
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/reclean_preview`, {
          method: "POST",
          headers: { "x-api-key": apiKey ?? "", "Content-Type": "application/json" },
          body: JSON.stringify({ save: false }),
          signal: controller.signal,
        });
        const data = await r.json();
        if (r.ok && data.status === "success") setRecleanPreview(data as RecleanPreview);
      } catch { /* The normal split preview still works if comparison is unavailable. */ }
    })();
    return () => controller.abort();
  }, [id, newMode, apiUrl, apiKey, previewNonce]);

  // ── Job polling ──

  const pollJob = React.useCallback((jid: string) => {
    if (jobPollRef.current) clearInterval(jobPollRef.current);
    const check = async () => {
      try {
        const r = await fetch(`${apiUrl}/analysis_job/${jid}`, {
          headers: { "x-api-key": apiKey ?? "" },
        });
        const data = await r.json();
        setJobStatus(data.job?.progress ?? data.job?.status ?? data.status);
        if (data.job?.status === "done") {
          if (jobPollRef.current) clearInterval(jobPollRef.current);
          jobPollRef.current = null;
          setJobId(null);
          await fetchRuns();
          if (data.job.run_id) setSelectedRun(data.job.run_id);
        } else if (data.job?.status === "failed") {
          if (jobPollRef.current) clearInterval(jobPollRef.current);
          jobPollRef.current = null;
          setJobId(null);
          setError("Analiza nie powiodła się: " + (data.job.error ?? ""));
        }
      } catch {
        // A transient connection problem must not detach a persistent job.
        setJobStatus("Oczekiwanie na backend…");
      }
    };
    void check();
    jobPollRef.current = setInterval(check, 5000);
  }, [apiUrl, apiKey, fetchRuns]);

  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${id}/analysis_job`, {
          headers: { "x-api-key": apiKey ?? "" },
        });
        const data = await response.json();
        if (!cancelled && data.job?.id) {
          setJobId(data.job.id);
          setJobStatus(data.job.progress ?? data.job.status);
          pollJob(data.job.id);
        }
      } catch { /* Existing runs remain usable when queue status is unavailable. */ }
    })();
    return () => {
      cancelled = true;
      if (jobPollRef.current) clearInterval(jobPollRef.current);
      jobPollRef.current = null;
    };
  }, [id, apiUrl, apiKey, pollJob]);

  // ── Analysis ──

  const startAnalysis = async (
    modeOverride?: string, splitOnlyOverride?: boolean, scopeChapterOverride?: number | null,
    recleanOverride?: boolean,
  ) => {
    if (!id) return;
    setError(""); setJobStatus("starting");
    const mode = modeOverride ?? newMode;
    // undefined = use the panel selection; null = force whole document
    const scope = scopeChapterOverride !== undefined
      ? scopeChapterOverride
      : (mode === "article" && scopeChapter !== "" ? scopeChapter : null);
    try {
      const r = await fetch(`${apiUrl}/document/${id}/analyze_chunks`, {
        method: "POST", headers,
        body: JSON.stringify({
          model: newModel, chunk_size: chunkSize,
          mode,
          split_only: splitOnlyOverride ?? splitOnly,
          preclean: mode === "article" && !(splitOnlyOverride ?? splitOnly) && preclean,
          reclean: mode === "article" && (recleanOverride ?? useRecleaned),
          ...(scope !== null ? { scope_chapter: scope } : {}),
        }),
      });
      const data = await r.json();
      if (data.job_id) { setJobId(data.job_id); setJobStatus("running"); pollJob(data.job_id); }
      else { setError("Nie udało się uruchomić analizy"); setJobStatus(null); }
    } catch { setError("Błąd połączenia"); setJobStatus(null); }
  };

  const previewReclean = async (save = false) => {
    if (!id) return;
    if (save && !window.confirm("Zapisać oczyszczony tekst w dokumencie? Ta operacja nadpisze bieżące pole tekstowe.")) return;
    setRecleaning(true); setError(""); setInfo("");
    try {
      const r = await fetch(`${apiUrl}/document/${id}/reclean_preview`, {
        method: "POST", headers, body: JSON.stringify({ save }),
      });
      const data = await r.json();
      if (!r.ok || data.status !== "success") throw new Error(data.message || "Nie udało się przeczyścić tekstu");
      setRecleanPreview(data as RecleanPreview);
      setPreviewNonce(n => n + 1);
      if (save) {
        setUseRecleaned(false);
        setInfo(`Zapisano oczyszczony tekst w polu ${data.source_field}.`);
      } else {
        const confirmed = window.confirm(
          `Ponowne czyszczenie: ${data.before_length.toLocaleString("pl")} → ${data.after_length.toLocaleString("pl")} znaków, `
          + `${data.removed_line_count} usuniętych lub zmienionych linii.\n\nUtworzyć teraz nowy run „tylko podział”?`,
        );
        if (confirmed) {
          setUseRecleaned(true);
          setInfo("Tworzę nowy podział z oczyszczonego tekstu…");
          await startAnalysis("article", true, null, true);
        } else {
          setUseRecleaned(false);
          setInfo("Podgląd gotowy. Nowy run nie został utworzony.");
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd ponownego czyszczenia tekstu");
    } finally {
      setRecleaning(false);
    }
  };

  const prepareSplit = async () => {
    const cleanupNeeded = !!recleanPreview && (
      recleanPreview.before_length !== recleanPreview.after_length
      || recleanPreview.before_line_count !== recleanPreview.after_line_count
      || recleanPreview.removed_line_count > 0
    );
    if (cleanupNeeded) await previewReclean(false);
    else await startAnalysis("article", true, null, false);
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

  const togglePhotoBlockMark = (chunkId: number, indices: number[]) => {
    setLineEdits(prev => {
      const cur = new Set(prev[chunkId] ?? []);
      const restore = indices.every(idx => cur.has(idx));
      indices.forEach(idx => restore ? cur.delete(idx) : cur.add(idx));
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
    const removedLines = lines.filter((_, i) => marked.has(i)).map(l => l.trim()).filter(Boolean);
    setSavingLines(prev => ({ ...prev, [chunk.id]: true }));
    const res = await patchChunk(chunk.id, {
      original_text: newText,
      ...(!newText.trim() ? { type: "SZUM", status: "skipped", topic: "Usunięty fragment" } : {}),
      ...(removeFromDocument && removedLines.length ? { remove_lines_from_document: removedLines } : {}),
    });
    setSavingLines(prev => ({ ...prev, [chunk.id]: false }));
    if (res?.status === "success") {
      clearLineMarks(chunk.id);
      const sourceCount = res.document_lines_removed ?? 0;
      if (!newText.trim()) {
        setInfo(`Usunięto całą treść chunka #${chunk.position} i oznaczono go jako SZUM${sourceCount > 0 ? `; usunięto też ${sourceCount} linii ze źródła` : ""}.`);
      } else if (sourceCount > 0) {
        setInfo(`Usunięto ${sourceCount} linii z dokumentu źródłowego`);
      }
      if (sourceCount > 0) {
        setPreviewNonce(n => n + 1);
      }
    }
  };

  const replaceChunkText = async (chunk: Chunk, text: string): Promise<boolean> => {
    if (!text.trim() || text === (chunk.original_text ?? "")) return text === (chunk.original_text ?? "");
    setSavingLines(prev => ({ ...prev, [chunk.id]: true }));
    const res = await patchChunk(chunk.id, {
      original_text: text,
      ...(chunk.type === "TEMAT" ? { status: "needs_reanalysis" } : {}),
    });
    setSavingLines(prev => ({ ...prev, [chunk.id]: false }));
    if (res?.status === "success") {
      clearLineMarks(chunk.id);
      setInfo(`Zapisano ręczną edycję linii w chunku #${chunk.position}.`);
      return true;
    }
    setError("Nie udało się zapisać edycji linii.");
    return false;
  };

  const saveAllVisibleLineRemovals = async () => {
    const targets = visibleChunks.filter(c => (lineEdits[c.id]?.size ?? 0) > 0);
    if (!targets.length) return;
    for (const chunk of targets) await saveLineRemovals(chunk, true);
    setInfo(`Zapisano usunięcie zaznaczonych linii w ${targets.length} widocznych chunkach.`);
  };

  const markLineSplit = (chunkId: number, lineIdx: number) => {
    setLineSplitStates(prev => {
      const indices = new Set(prev[chunkId]?.lineIndices ?? []);
      if (indices.has(lineIdx)) indices.delete(lineIdx); else indices.add(lineIdx);
      if (indices.size === 0) { const n = { ...prev }; delete n[chunkId]; return n; }
      return { ...prev, [chunkId]: { lineIndices: indices } };
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
          split_at_lines: [...st.lineIndices].sort((a, b) => a - b),
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
    try {
      const r = await fetch(`${apiUrl}/chunk/${chunk.id}/merge_with_next`, { method: "POST", headers });
      const data = await r.json();
      if (data.status === "success") {
        if (selectedRun !== null) await fetchChunks(selectedRun);
      } else { setError("Błąd scalania: " + (data.message ?? "")); }
    } catch { setError("Błąd połączenia przy scalaniu"); }
  };

  const deleteNoiseChunk = async (chunk: Chunk) => {
    if (chunk.type === "TEMAT" || deletingChunks[chunk.id]) return;
    setDeletingChunks(prev => ({ ...prev, [chunk.id]: true }));
    setError("");
    try {
      const r = await fetch(`${apiUrl}/chunk/${chunk.id}`, { method: "DELETE", headers });
      const data = await r.json();
      if (data.status === "success") {
        setInfo(`Usunięto chunk #${chunk.position} (${chunk.type}) z bieżącego runu.`);
        if (selectedRun !== null) await fetchChunks(selectedRun);
      } else {
        setError("Nie udało się usunąć chunka: " + (data.message ?? ""));
      }
    } catch {
      setError("Błąd połączenia przy usuwaniu chunka");
    } finally {
      setDeletingChunks(prev => ({ ...prev, [chunk.id]: false }));
    }
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

  // ── Sections (book view) ──

  const mergeFullChunks = (full: Chunk[]) => {
    setChunks(prev => {
      const byId = new Map(full.map(f => [f.id, f]));
      const merged = prev.map(c => byId.get(c.id) ?? c);
      const known = new Set(prev.map(c => c.id));
      full.forEach(f => { if (!known.has(f.id)) merged.push(f); });
      return merged.sort((a, b) => a.position - b.position);
    });
    setTopicEdits(prev => {
      const n = { ...prev };
      full.forEach(c => { n[c.id] = c.topic ?? ""; });
      return n;
    });
    setShowCorrected(prev => {
      const n = { ...prev };
      full.forEach(c => { n[c.id] = !!c.corrected_text; });
      return n;
    });
  };

  const toggleSection = async (ts: TopicSection) => {
    const expanding = !expandedSections.has(ts.id);
    setExpandedSections(prev => {
      const n = new Set(prev);
      if (expanding) n.add(ts.id); else n.delete(ts.id);
      return n;
    });
    if (!expanding || loadedSections.has(ts.id) || selectedRun === null) return;
    setLoadingSections(prev => ({ ...prev, [ts.id]: true }));
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/chunks?section_id=${ts.id}`, { headers });
      const data = await r.json();
      if (data.status === "success") {
        mergeFullChunks(data.chunks ?? []);
        setLoadedSections(prev => new Set([...prev, ts.id]));
      } else { setError("Błąd ładowania chunków sekcji"); }
    } catch { setError("Błąd połączenia przy ładowaniu sekcji"); }
    finally { setLoadingSections(prev => ({ ...prev, [ts.id]: false })); }
  };

  const switchToFlatFull = async () => {
    if (selectedRun === null) return;
    setLoading(true);
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/chunks`, { headers });
      const data = await r.json();
      mergeFullChunks(data.chunks ?? []);
      setSectionView(false);
      setFlatPaged(false);
    } catch { setError("Błąd ładowania pełnej listy chunków"); }
    finally { setLoading(false); }
  };

  const saveSectionTitle = async (sectionId: number) => {
    const title = (sectionTitleEdits[sectionId] ?? "").trim();
    if (!title) return;
    setSavingSectionTitle(true);
    try {
      const r = await fetch(`${apiUrl}/topic_section/${sectionId}`, {
        method: "PATCH", headers, body: JSON.stringify({ title }),
      });
      const data = await r.json();
      if (data.status === "success") {
        setTopicSections(prev => prev.map(ts =>
          ts.id === sectionId ? { ...ts, title: data.topic_section.title } : ts));
        setEditingSectionId(null);
      } else { setError("Błąd zapisu tytułu sekcji"); }
    } catch { setError("Błąd połączenia przy zapisie tytułu sekcji"); }
    finally { setSavingSectionTitle(false); }
  };

  const loadMoreChunks = async () => {
    if (selectedRun === null || loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await fetch(
        `${apiUrl}/analysis_run/${selectedRun}/chunks?offset=${chunks.length}&limit=${CHUNK_PAGE_SIZE}`,
        { headers });
      const data = await r.json();
      mergeFullChunks(data.chunks ?? []);
    } catch { setError("Błąd doładowania chunków"); }
    finally { setLoadingMore(false); }
  };

  // ── Run workflow status ──

  const setRunWorkflowStatus = async (status: string) => {
    if (selectedRun === null) return;
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}`, {
        method: "PATCH", headers, body: JSON.stringify({ status }),
      });
      const data = await r.json();
      if (data.status === "success") {
        setRunStatus(data.run.status);
        setRuns(prev => prev.map(rr => rr.id === selectedRun ? { ...rr, status: data.run.status } : rr));
        if (data.embedding_job_id) {
          setEmbedJobId(data.embedding_job_id);
          setEmbedJobStatus("running");
          pollEmbeddingJob(data.embedding_job_id);
          setInfo("Review zamknięty — automatycznie generuję embeddingi z zatwierdzonych chunków TEMAT.");
        } else if (status === "reviewed" && approvedCount === 0) {
          setInfo("Review zamknięty, ale nie utworzono embeddingów: brak zatwierdzonych chunków TEMAT.");
        }
      } else { setError("Błąd zmiany statusu analizy"); }
    } catch { setError("Błąd połączenia przy zmianie statusu analizy"); }
  };

  const applyCleanupAndResplit = async () => {
    if (selectedRun === null || applyingCleanup || jobId) return;
    if (!window.confirm(
      "Nadpisać tekst źródłowy dokumentu treścią chunków TEMAT i ŹRÓDŁA (REKLAMA/SZUM i usunięte linie znikną),\n"
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
      await startAnalysis("article", true, null);
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

  // Detect speakers from one specific chunk only — useful when the reviewer has
  // already split out just the self-introductions, so the surrounding chunks
  // (chit-chat, sponsor reads) don't need to be sent to the LLM too.
  const extractSpeakersFromChunk = async (chunkId: number) => {
    if (!selectedRun) return;
    setExtractingSpeakerFor(chunkId);
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/extract_speakers`, {
        method: "POST", headers,
        body: JSON.stringify({ chunk_ids: [chunkId] }),
      });
      const data = await r.json();
      if (data.status === "success") setSpeakers(data.speakers ?? []);
      else setError("Błąd wykrywania rozmówców: " + (data.message ?? ""));
    } catch { setError("Błąd połączenia przy wykrywaniu rozmówców"); }
    finally { setExtractingSpeakerFor(null); }
  };

  // Detect the article author (byline) from one specific chunk. Unlike speaker
  // detection, no position limit — a byline can appear at either the start or
  // the end of an article. Saves directly to doc.author (backend commits it).
  const applyAuthorResponse = (data: { author: string; author_source?: string; author_persons?: AuthorPerson[] }) => {
    setDocAuthor(data.author);
    setAuthorInput(data.author);
    setDocAuthorSource(data.author_source ?? "llm");
    setAuthorPersons(data.author_persons ?? []);
  };

  const extractAuthorFromChunk = async (chunkId: number) => {
    if (!selectedRun) return;
    setExtractingAuthorFor(chunkId);
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/extract_author`, {
        method: "POST", headers,
        body: JSON.stringify({ chunk_ids: [chunkId] }),
      });
      const data = await r.json();
      if (data.status === "success" && data.author) {
        applyAuthorResponse(data);
        setInfo(`Ustawiono autora: ${data.author}`);
      }
      else if (data.status === "success") setError("Nie udało się rozpoznać autora w tym chunku");
      else setError("Błąd wykrywania autora: " + (data.message ?? ""));
    } catch { setError("Błąd połączenia przy wykrywaniu autora"); }
    finally { setExtractingAuthorFor(null); }
  };

  // Detect the publication date from one specific chunk. Mirrors extractAuthorFromChunk —
  // no position limit, saves directly to doc.date_from (backend commits it).
  const extractDateFromChunk = async (chunkId: number) => {
    if (!selectedRun) return;
    setExtractingDateFor(chunkId);
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/extract_publication_date`, {
        method: "POST", headers,
        body: JSON.stringify({ chunk_ids: [chunkId] }),
      });
      const data = await r.json();
      if (data.status === "success" && data.date_from) {
        setDocDateFrom(data.date_from);
        setDocDateFromSource(data.date_from_source ?? "llm");
        setDateInput(data.date_from);
        setInfo(`Ustawiono datę publikacji: ${data.date_from}`);
      }
      else if (data.status === "success") setError("Nie udało się rozpoznać daty publikacji w tym chunku");
      else setError("Błąd wykrywania daty publikacji: " + (data.message ?? ""));
    } catch { setError("Błąd połączenia przy wykrywaniu daty publikacji"); }
    finally { setExtractingDateFor(null); }
  };

  // Manually save the date typed into the calendar input next to the "Data
  // publikacji" badge — the reviewer copying a date off the original page,
  // as opposed to extractDateFromChunk's LLM-based detection above.
  const saveDateFrom = async () => {
    if (!id || !dateInput) return;
    setSavingDate(true);
    try {
      const r = await fetch(`${apiUrl}/document/${id}/date_from`, {
        method: "POST", headers, body: JSON.stringify({ date_from: dateInput }),
      });
      const data = await r.json();
      if (data.status === "success") {
        setDocDateFrom(data.date_from);
        setDocDateFromSource(data.date_from_source ?? "manual");
        setInfo(`Ustawiono datę publikacji: ${data.date_from}`);
      } else setError("Błąd zapisu daty publikacji: " + (data.message ?? ""));
    } catch { setError("Błąd połączenia przy zapisie daty publikacji"); }
    finally { setSavingDate(false); }
  };

  // Manually save the byline typed/pasted into the input next to the "Autor"
  // badge — the reviewer copying the byline off the original page (co-authors
  // separated by commas or "i"/"oraz"), as opposed to the LLM detection above.
  const saveAuthor = async () => {
    if (!id || !authorInput.trim()) return;
    setSavingAuthor(true);
    try {
      const r = await fetch(`${apiUrl}/document/${id}/author`, {
        method: "POST", headers, body: JSON.stringify({ author: authorInput }),
      });
      const data = await r.json();
      if (data.status === "success") {
        applyAuthorResponse({ ...data, author_source: data.author_source ?? "manual" });
        setInfo(`Ustawiono autora: ${data.author}`);
      } else setError("Błąd zapisu autora: " + (data.message ?? ""));
    } catch { setError("Błąd połączenia przy zapisie autora"); }
    finally { setSavingAuthor(false); }
  };

  const extractAuthorFromLine = async (chunk: Chunk, lineIdx: number) => {
    if (!selectedRun) return;
    const lines = (chunk.original_text ?? "").split("\n");
    const contextText = lines.slice(Math.max(0, lineIdx - 2), lineIdx + 3).join("\n");
    setExtractingAuthorLine({ chunkId: chunk.id, lineIdx });
    setError("");
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/extract_author`, {
        method: "POST", headers, body: JSON.stringify({ context_text: contextText }),
      });
      const data = await r.json();
      if (data.status === "success" && data.author) {
        applyAuthorResponse(data);
        setInfo(`Ustawiono autora: ${data.author}. Linię autora możesz teraz oznaczyć × i usunąć.`);
      } else if (data.status === "success") setError("Nie udało się rozpoznać autora w tym kontekście");
      else setError("Błąd wykrywania autora: " + (data.message ?? ""));
    } catch { setError("Błąd połączenia przy wykrywaniu autora"); }
    finally { setExtractingAuthorLine(null); }
  };

  // ── Quality (staranność) + extraction issue report ──

  const computeQuality = async () => {
    if (!id || selectedRun === null || computingQuality) return;
    setComputingQuality(true);
    setError("");
    try {
      const r = await fetch(`${apiUrl}/document/${id}/quality`, {
        method: "POST", headers, body: JSON.stringify({ run_id: selectedRun }),
      });
      const data = await r.json();
      if (data.status === "success") {
        setDocQuality(data.quality);
        setInfo(`Oceniono staranność: ${data.quality.score}/100`);
      } else { setError("Błąd oceny staranności: " + (data.message ?? "")); }
    } catch { setError("Błąd połączenia przy ocenie staranności"); }
    finally { setComputingQuality(false); }
  };

  const refreshCitedPublications = async (chunk: Chunk) => {
    if (!id || refreshingCitationsFor !== null) return;
    setRefreshingCitationsFor(chunk.id); setError("");
    try {
      const r = await fetch(`${apiUrl}/document/${id}/cited_publications`, {
        method: "POST", headers, body: JSON.stringify({ chunk_ids: [chunk.id] }),
      });
      const data = await r.json();
      if (data.status === "success") {
        const citations = (data.entries ?? []).filter((entry: { chunk_id?: number }) => entry.chunk_id === chunk.id);
        setChunks(prev => prev.map(item => item.id === chunk.id
          ? { ...item, cited_publications: citations } : item));
        setInfo(`Z chunka #${chunk.position} zapisano ${data.refreshed_count} cytowanych publikacji; dokument ma łącznie ${data.count}.`);
      }
      else setError("Błąd zapisu cytowanych publikacji: " + (data.message ?? ""));
    } catch { setError("Błąd połączenia przy zapisie cytowanych publikacji"); }
    finally { setRefreshingCitationsFor(null); }
  };

  const reportExtractionIssue = async () => {
    if (!id || reportingIssue) return;
    if (!window.confirm(
      "Zgłosić: artykuł błędnie obcięty względem oryginału?\n"
      + "Dokument wróci do kolejki NEED_MANUAL_REVIEW z błędem ARTICLE_TRUNCATED."
    )) return;
    setReportingIssue(true);
    setError("");
    try {
      const r = await fetch(`${apiUrl}/document/${id}/report_extraction_issue`, { method: "POST", headers });
      const data = await r.json();
      if (data.status === "success") {
        setInfo("Zgłoszono błędne obcięcie artykułu — dokument trafił do kolejki ręcznej analizy (NEED_MANUAL_REVIEW).");
      } else { setError("Błąd zgłoszenia: " + (data.message ?? "")); }
    } catch { setError("Błąd połączenia przy zgłaszaniu"); }
    finally { setReportingIssue(false); }
  };

  // ── Embeddings ──

  const pollEmbeddingJob = React.useCallback((jid: string) => {
    const interval = setInterval(async () => {
      try {
        const r = await fetch(`${apiUrl}/embedding_job/${jid}`, { headers });
        const data = await r.json();
        setEmbedJobStatus(data.job?.status ?? data.status);
        if (data.job?.status === "done") {
          clearInterval(interval);
          setEmbedJobId(null);
          const res = data.job.result ?? {};
          setInfo(`Embeddingi: ${res.embeddings_created ?? 0} utworzonych z ${res.chunks_considered ?? 0} zatwierdzonych chunków`);
          if (selectedRun !== null) await fetchChunks(selectedRun);
        } else if (data.job?.status === "failed") {
          clearInterval(interval);
          setEmbedJobId(null);
          setError("Generowanie embeddingów nie powiodło się: " + (data.job.error ?? ""));
        }
      } catch {
        clearInterval(interval);
        setEmbedJobId(null);
      }
    }, 3000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, apiKey, selectedRun, fetchChunks]);

  const generateEmbeddings = async () => {
    if (selectedRun === null || embedJobId) return;
    setError(""); setEmbedJobStatus("starting");
    try {
      const r = await fetch(`${apiUrl}/analysis_run/${selectedRun}/generate_embeddings`, { method: "POST", headers });
      const data = await r.json();
      if (data.job_id) { setEmbedJobId(data.job_id); setEmbedJobStatus("running"); pollEmbeddingJob(data.job_id); }
      else { setError("Nie udało się uruchomić generowania embeddingów"); setEmbedJobStatus(null); }
    } catch { setError("Błąd połączenia przy generowaniu embeddingów"); setEmbedJobStatus(null); }
  };

  const goToNextDocument = async () => {
    if (!id || loadingNextDocument) return;
    setLoadingNextDocument(true); setError("");
    try {
      const r = await fetch(`${apiUrl}/document/${id}/next_for_analysis`, { headers });
      const data = await r.json();
      if (r.ok && data.document?.id) {
        window.location.assign(`/chunks/${data.document.id}`);
      } else {
        setInfo("Brak kolejnych dokumentów z niezakończonym review.");
      }
    } catch {
      setError("Nie udało się pobrać następnego dokumentu do analizy.");
    } finally {
      setLoadingNextDocument(false);
    }
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
    && (!filterUnprocessed || (c.type === "TEMAT" && (c.obsidian_note_paths?.length ?? 0) === 0))
  );
  const visibleMarkedLineCount = visibleChunks.reduce((sum, c) => sum + (lineEdits[c.id]?.size ?? 0), 0);
  const embeddedCount = tematChunks.filter(c => c.has_embeddings === true).length;
  const reviewReady = tematChunks.length > 0 && unapprovedTematCount === 0 && chunksToAnalyze.length === 0;
  const workflowBusy = !!jobId || reanalyzingAll || approvingAll || !!embedJobId;
  const analyzedTematCount = tematChunks.filter(c => c.summary).length;
  // Preclean leaves REKLAMA/SZUM chunks behind; a clean article leaves none,
  // so once the LLM analysis produced summaries the detection step is also done.
  const noiseMarkingDone = reklamaCount > 0 || analyzedTematCount > 0 || runStatus === "reviewed";
  const processComplete = runStatus === "reviewed" && embeddedCount > 0 && !embedJobId;

  // ── User notes: match notes to chunks of the selected run ──
  // Direct match by chunk_id; reader notes (or notes from other runs) fall back
  // to a quote search in the chunk text (skipped for lite chunks without texts).
  const chunkNotes = React.useMemo(() => {
    const byChunk = new Map<number, UserNote[]>();
    if (!userId || notes.length === 0) return byChunk;
    const runChunkIds = new Set(chunks.map(c => c.id));
    for (const n of notes) {
      if (n.chunk_id !== null && runChunkIds.has(n.chunk_id)) {
        byChunk.set(n.chunk_id, [...(byChunk.get(n.chunk_id) ?? []), n]);
        continue;
      }
      const quote = normalizeWs(n.anchor_quote);
      for (const c of chunks) {
        const text = c.corrected_text ?? c.original_text;
        if (text && normalizeWs(text).includes(quote)) {
          byChunk.set(c.id, [...(byChunk.get(c.id) ?? []), n]);
          break;
        }
      }
    }
    return byChunk;
  }, [notes, chunks, userId]);

  const onChunkTextSelected = (chunkId: number) => {
    if (!userId) return;
    const pending = pendingNoteFromSelection("p,div");
    if (pending) setPendingNote({ ...pending, chunkId });
  };

  const saveChunkNote = async (noteText: string, stance: string | null) => {
    if (!pendingNote || !noteText) return;
    // chapter_position: chapter-scoped runs store the chapter title in run.scope
    const scope = runs.find(r => r.id === selectedRun)?.scope;
    const chapter = scope ? chapters.find(ch => ch.title === scope)?.position ?? null : null;
    const ok = await createNote({
      anchor_quote: pendingNote.quote,
      anchor_prefix: pendingNote.prefix,
      anchor_suffix: pendingNote.suffix,
      chapter_position: chapter,
      run_id: selectedRun,
      chunk_id: pendingNote.chunkId,
      note_text: noteText,
      stance,
    });
    if (ok) {
      setExpandedNoteChunks(prev => new Set([...prev, pendingNote.chunkId]));
      setPendingNote(null);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────

  // Karta pojedynczego chunka — używana w widoku płaskim i w accordionie sekcji
  const renderChunkCard = (chunk: Chunk) => {
        const hasCorrected = !!chunk.corrected_text;
        const chunkLength = chunk.text_length ?? (chunk.corrected_text ?? chunk.original_text ?? "").length;
        const nextChunk = chunks.find(c => c.position === chunk.position + 1);
        const nextChunkLength = nextChunk
          ? (nextChunk.text_length ?? (nextChunk.corrected_text ?? nextChunk.original_text ?? "").length)
          : 0;
        const mergedLength = chunkLength + nextChunkLength;
        const mergeExceedsTarget = mergedLength > chunkSize;
        const isCorrectedView = showCorrected[chunk.id] ?? hasCorrected;
        const isReanalyzing = reanalyzing[chunk.id] ?? false;
        const splitSt = splitStates[chunk.id];
        const lineSplitSt = lineSplitStates[chunk.id];
        const chunkSegs = segments.slice(chunk.seg_start ?? 0, chunk.seg_end ?? segments.length);
        const myNotes = chunkNotes.get(chunk.id) ?? [];
        const notesExpanded = expandedNoteChunks.has(chunk.id);

        return (
          <div key={chunk.id} style={{ marginBottom: 18, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>

            {/* Nagłówek */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "#f1f5f9", borderBottom: "1px solid #e2e8f0", fontSize: "0.82em", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 600, color: "#334155", minWidth: 24 }}>#{chunk.position}</span>
              <span
                title={`Dokładny rozmiar: ${chunkLength.toLocaleString("pl-PL")} znaków; około ${Math.ceil(chunkLength / 4).toLocaleString("pl-PL")} tokenów`}
                style={{ color: "#64748b", fontSize: "0.9em", whiteSpace: "nowrap" }}
              >
                {chunkLength >= 1000 ? `${(chunkLength / 1000).toLocaleString("pl-PL", { maximumFractionDigits: 1 })} tys. zn` : `${chunkLength} zn`}
              </span>

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

              {!!chunk.obsidian_note_paths?.length && (
                <span style={{ color: "#7c3aed", display: "inline-flex", alignItems: "center", gap: 4 }}>
                  📝
                  {chunk.obsidian_note_paths.map((notePath, i) => (
                    <React.Fragment key={notePath}>
                      {i > 0 && ","}
                      <a
                        href={buildObsidianNoteUrl(notePath)}
                        title={`Otwórz w Obsidianie: ${notePath}`}
                        style={{ color: "#7c3aed" }}
                      >
                        {notePath.split("/").pop()?.replace(/\.md$/i, "")}
                      </a>
                    </React.Fragment>
                  ))}
                </span>
              )}
              {myNotes.length > 0 && (
                <span
                  onClick={() => setExpandedNoteChunks(prev => {
                    const next = new Set(prev);
                    if (next.has(chunk.id)) next.delete(chunk.id); else next.add(chunk.id);
                    return next;
                  })}
                  title={`${myNotes.length} ${myNotes.length === 1 ? "notatka" : "notatki/notatek"} — kliknij aby ${notesExpanded ? "zwinąć" : "rozwinąć"}`}
                  style={{ color: "#0369a1", cursor: "pointer", fontWeight: 600 }}
                >
                  💬 {myNotes.length}
                </span>
              )}
              {chunk.has_embeddings != null && (
                <span title={chunk.has_embeddings ? "Ma embeddingi" : "Brak embeddingów"}>
                  {chunk.has_embeddings ? "🟢" : "⚪"}
                </span>
              )}
              {!!chunk.cited_publications?.length && (
                <span title="Publikacje wykryte i zapisane z tego chunka"
                  style={{ color: "#6d28d9", fontWeight: 600 }}>
                  📚 {chunk.cited_publications.length}
                </span>
              )}

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
              {runMode === "transcript" && chunk.position <= SPEAKER_DETECT_CHUNK_LIMIT && (
                <button
                  onClick={() => extractSpeakersFromChunk(chunk.id)}
                  disabled={extractingSpeakerFor === chunk.id}
                  title="Wykryj rozmówców tylko z tego chunka (np. gdy przedstawienie się zostało wydzielone do osobnego chunka)"
                  style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em", color: "#64748b" }}
                >
                  {extractingSpeakerFor === chunk.id ? "🎙 Wykrywam…" : "🎙 Wykryj"}
                </button>
              )}
              {runMode === "article" && (
                <button
                  onClick={() => extractAuthorFromChunk(chunk.id)}
                  disabled={extractingAuthorFor === chunk.id}
                  title="Wykryj autora artykułu (byline) z tego chunka i zapisz go w dokumencie"
                  style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em", color: "#64748b" }}
                >
                  {extractingAuthorFor === chunk.id ? "✍️ Wykrywam…" : "✍️ Autor"}
                </button>
              )}
              {runMode === "article" && (
                <button
                  onClick={() => extractDateFromChunk(chunk.id)}
                  disabled={extractingDateFor === chunk.id}
                  title="Wykryj datę publikacji artykułu z tego chunka i zapisz ją w dokumencie"
                  style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em", color: "#64748b" }}
                >
                  {extractingDateFor === chunk.id ? "📅 Wykrywam…" : "📅 Data"}
                </button>
              )}
              {runMode === "article" && (
                <button
                  onClick={() => refreshCitedPublications(chunk)}
                  disabled={refreshingCitationsFor !== null}
                  title="Odczytaj PMID, PMCID i DOI tylko z tego chunka; publikacje zostaną przypisane do całego dokumentu"
                  style={{ padding: "2px 8px", border: "1px solid #c4b5fd", borderRadius: 4, background: "#f5f3ff", cursor: "pointer", fontSize: "0.82em", color: "#6d28d9" }}
                >
                  {refreshingCitationsFor === chunk.id ? "📚 Zapisuję…" : "📚 Cytowania"}
                </button>
              )}
              {chunk.position < maxPosition && (
                <button
                  onClick={() => mergeWithNext(chunk)}
                  title={`Scal z chunkiem #${chunk.position + 1}: wynik ${mergedLength.toLocaleString("pl-PL")} znaków${mergeExceedsTarget ? ` (powyżej celu ${chunkSize.toLocaleString("pl-PL")})` : ""}`}
                  style={{
                    padding: "2px 8px", border: `1px solid ${mergeExceedsTarget ? "#f59e0b" : "#cbd5e1"}`,
                    borderRadius: 4, background: mergeExceedsTarget ? "#fffbeb" : "#fff", cursor: "pointer",
                    fontSize: "0.82em", color: mergeExceedsTarget ? "#92400e" : "#64748b",
                  }}
                >
                  ⇣ Scal
                  {" → "}{mergedLength >= 1000
                    ? `${(mergedLength / 1000).toLocaleString("pl-PL", { maximumFractionDigits: 1 })} tys. zn`
                    : `${mergedLength} zn`}
                </button>
              )}
              <button
                onClick={() => chunk.type === "TEMAT"
                  ? setHiddenChunks(prev => new Set([...prev, chunk.id]))
                  : deleteNoiseChunk(chunk)}
                disabled={!!deletingChunks[chunk.id]}
                title={chunk.type === "TEMAT" ? "Ukryj ten chunk" : `Usuń chunk ${chunk.type} z bieżącego runu`}
                style={{
                  padding: "2px 8px", border: `1px solid ${chunk.type === "TEMAT" ? "#cbd5e1" : "#fca5a5"}`,
                  borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.82em",
                  color: chunk.type === "TEMAT" ? "#64748b" : "#b91c1c", marginLeft: "auto",
                }}
              >
                {deletingChunks[chunk.id] ? "…" : chunk.type === "TEMAT" ? "✕" : "🗑"}
              </button>
            </div>

            {/* Treść: poprawiony tekst → segmenty transkrypcji → surowy tekst (artykuły) */}
            <div style={{ padding: "12px 14px", fontSize: "0.88em", lineHeight: 1.6 }}
              onMouseUp={() => onChunkTextSelected(chunk.id)}>
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
                  photoCaptionLines={new Set(chunk.photo_caption_line_indices ?? [])}
                  splitLineIndices={lineSplitStates[chunk.id]?.lineIndices ?? new Set()}
                  saving={savingLines[chunk.id] ?? false}
                  detectingAuthorLine={extractingAuthorLine?.chunkId === chunk.id ? extractingAuthorLine.lineIdx : null}
                  onToggleLine={idx => toggleLineMark(chunk.id, idx)}
                  onTogglePhotoBlock={indices => togglePhotoBlockMark(chunk.id, indices)}
                  onMarkSplit={idx => markLineSplit(chunk.id, idx)}
                  onDetectAuthor={idx => extractAuthorFromLine(chunk, idx)}
                  onReplaceText={text => replaceChunkText(chunk, text)}
                  onSave={removeFromDoc => saveLineRemovals(chunk, removeFromDoc)}
                  onCancel={() => clearLineMarks(chunk.id)}
                />
              )}
            </div>

            {!!chunk.cited_publications?.length && (
              <div style={{ margin: "0 14px 12px", padding: "8px 10px", background: "#f5f3ff", border: "1px solid #ddd6fe", borderRadius: 5 }}>
                <strong style={{ display: "block", color: "#6d28d9", fontSize: "0.8em", marginBottom: 5 }}>📚 Wykryte cytowane publikacje</strong>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {chunk.cited_publications.map(publication => {
                    const identifier = publication.pmid ? `PMID ${publication.pmid}`
                      : publication.pmcid ? publication.pmcid
                      : publication.doi ? `DOI ${publication.doi}` : `publikacja #${publication.publication_id}`;
                    return <a key={publication.id} href={publication.canonical_url} target="_blank" rel="noreferrer"
                      title={publication.title || identifier}
                      style={{ padding: "2px 7px", borderRadius: 4, background: "#fff", color: "#6d28d9", fontSize: "0.8em", fontWeight: 600 }}>
                      {identifier} ↗
                    </a>;
                  })}
                </div>
              </div>
            )}

            {/* Moje notatki do tego chunka */}
            {notesExpanded && myNotes.length > 0 && (
              <div style={{ margin: "0 14px 14px", background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 5 }}>
                <strong style={{ fontSize: "0.8em", color: "#0369a1", display: "block", padding: "6px 10px 0" }}>
                  💬 Moje notatki
                </strong>
                {myNotes.map(n => (
                  <NoteRow
                    key={n.id}
                    note={n}
                    header={<>{STANCE_ICON[n.stance ?? ""] ?? "📝"}{n.chapter_position ? ` rozdz. ${n.chapter_position}` : ""}</>}
                    onSaveText={saveNoteText}
                    onDelete={deleteNote}
                  />
                ))}
              </div>
            )}

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
                      <option value="ZRODLA">ŹRÓDŁA</option>
                      <option value="SZUM">SZUM</option>
                    </select>
                  </label>
                  <label>Część 2 (po):&nbsp;
                    <select value={splitSt.secondType}
                      onChange={e => setSplitStates(prev => ({ ...prev, [chunk.id]: { ...prev[chunk.id], secondType: e.target.value as ChunkType } }))}
                      style={{ padding: "2px 6px", borderRadius: 3 }}>
                      <option value="TEMAT">TEMAT</option>
                      <option value="ZRODLA">ŹRÓDŁA</option>
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
                <strong style={{ color: "#92400e" }}>✂ Punkty podziału: {[...lineSplitSt.lineIndices].sort((a, b) => a - b).map(i => i + 1).join(", ")} ({lineSplitSt.lineIndices.size + 1} części)</strong>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
                  <span>Wszystkie nowe części otrzymają typ TEMAT.</span>
                  <button onClick={() => confirmLineSplit(chunk.id)} disabled={confirmingLineSplit[chunk.id]}
                    style={{ padding: "3px 12px", background: "#f97316", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer", fontWeight: "bold", fontSize: "0.82em" }}>
                    {confirmingLineSplit[chunk.id] ? "Dzielę…" : "Wykonaj podział"}
                  </button>
                  <button onClick={() => cancelLineSplit(chunk.id)}
                    style={{ padding: "3px 10px", background: "#e2e8f0", color: "#475569", border: "none", borderRadius: 3, cursor: "pointer", fontSize: "0.82em" }}>
                    Anuluj
                  </button>
                </div>
                <div style={{ color: "#92400e", fontSize: "0.8em", marginTop: 4 }}>Klikaj ✂ przy kolejnych liniach, aby dodać lub usunąć punkty. Części TEMAT dostaną status needs_reanalysis.</div>
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
  };


  // Any non-reviewed run means there's an analysis in progress — the top
  // "Rozpocznij analizę" button then starts an unrelated, additional run
  // rather than continuing it, so it's relabeled to make that explicit.
  const hasActiveRun = runs.some(r => r.status !== "reviewed");
  const cleanupNeeded = !!recleanPreview && (
    recleanPreview.before_length !== recleanPreview.after_length
    || recleanPreview.before_line_count !== recleanPreview.after_line_count
    || recleanPreview.removed_line_count > 0
  );
  const cleanupEvidence = (recleanPreview?.removed_lines_preview ?? []).join("\n");
  const cleanupSignals = [
    /Wybrane dla Ciebie|Regulamin|Polityka prywatności|©|TECH\.WP\.PL/i.test(cleanupEvidence) ? "stopka lub rekomendacje" : null,
    /REKLAMA|KONIEC REKLAMY/i.test(cleanupEvidence) ? "markery reklam" : null,
    /Zaloguj|Menu|Najnowsze|Odkryj/i.test(cleanupEvidence) ? "nawigacja" : null,
  ].filter((value): value is string => value !== null);
  const prepareButtonLabel = cleanupNeeded
    ? (runs.length > 0 ? "Przeczyść i podziel ponownie" : "Przeczyść i podziel")
    : (runs.length > 0 ? "Podziel ponownie" : "Podziel tekst");

  return (
    <div className={selectedRun !== null ? "chunks-page chunks-page--with-flow" : "chunks-page"}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 6, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>
          Przegląd chunków — {docTitle || `dokument #${id}`}
          {docType && <span style={{ fontWeight: 400, color: "#64748b", fontSize: "0.7em" }}> ({DOC_TYPE_LABELS[docType] ?? docType}, #{id})</span>}
        </h2>
        {runMode === "article" && (
          <span style={{ fontSize: "0.88em", padding: "3px 9px", borderRadius: 4, background: docAuthor ? "#f3e8ff" : "#f1f5f9", color: docAuthor ? "#6b21a8" : "#64748b", display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            Autor:{" "}
            {authorPersons.length > 0
              ? authorPersons.map((p, i) => (
                  <React.Fragment key={p.person_id}>
                    {i > 0 && <span>, </span>}
                    <NavLink to={`/persons/${p.person_id}`} target="_blank" rel="noreferrer"
                      title={p.description || "Podsumowanie autora i jego artykuły — otwórz w nowej karcie"}
                      style={{ color: "inherit", fontWeight: 700 }}>{p.name}</NavLink>
                  </React.Fragment>
                ))
              : <strong>{docAuthor || "nie wykryto"}</strong>}
            {docAuthor && docAuthorSource && (
              <span
                title={docAuthorSource === "manual"
                  ? "Wpisany ręcznie przez recenzenta — automatyka go nie znalazła"
                  : "Wykryty przez LLM z treści dokumentu"}
                style={{ fontSize: "0.85em", opacity: 0.75 }}
              >
                {docAuthorSource === "manual" ? "✍️" : "🤖"}
              </span>
            )}
            <input
              type="text"
              value={authorInput}
              onChange={e => setAuthorInput(e.target.value)}
              placeholder="Imię Nazwisko, Imię Nazwisko"
              title="Wpisz lub wklej autorów z oryginalnej strony — współautorów oddziel przecinkiem lub „i”"
              style={{ fontSize: "0.9em", padding: "1px 3px", border: "1px solid #cbd5e1", borderRadius: 3, width: 180 }}
            />
            <button
              onClick={saveAuthor}
              disabled={!authorInput.trim() || savingAuthor}
              title="Zapisz wpisanych autorów (utworzy też powiązania z rejestrem osób)"
              style={{ padding: "1px 7px", border: "1px solid #cbd5e1", borderRadius: 3, background: "#fff", cursor: "pointer", fontSize: "0.9em", color: "#64748b" }}
            >
              {savingAuthor ? "…" : "💾"}
            </button>
          </span>
        )}
        {runMode === "article" && (
          <span style={{ fontSize: "0.88em", padding: "3px 9px", borderRadius: 4, background: docDateFrom ? "#f3e8ff" : "#f1f5f9", color: docDateFrom ? "#6b21a8" : "#64748b", display: "inline-flex", alignItems: "center", gap: 6 }}>
            Data publikacji: <strong>{docDateFrom || "nie wykryto"}</strong>
            {docDateFrom && docDateFromSource && (
              <span
                title={docDateFromSource === "manual"
                  ? "Wpisana ręcznie przez recenzenta — automatyka jej nie znalazła"
                  : "Wykryta przez LLM z treści chunka"}
                style={{ fontSize: "0.85em", opacity: 0.75 }}
              >
                {docDateFromSource === "manual" ? "✍️" : "🤖"}
              </span>
            )}
            <input
              type="date"
              value={dateInput}
              onChange={e => setDateInput(e.target.value)}
              title="Wpisz datę publikacji ręcznie, np. z kalendarza na oryginalnej stronie"
              style={{ fontSize: "0.9em", padding: "1px 3px", border: "1px solid #cbd5e1", borderRadius: 3 }}
            />
            <button
              onClick={saveDateFrom}
              disabled={!dateInput || savingDate}
              title="Zapisz wpisaną datę jako datę publikacji dokumentu"
              style={{ padding: "1px 7px", border: "1px solid #cbd5e1", borderRadius: 3, background: "#fff", cursor: "pointer", fontSize: "0.9em", color: "#64748b" }}
            >
              {savingDate ? "…" : "💾"}
            </button>
          </span>
        )}
        {EDITOR_TYPES.includes(docType) ? (
          <NavLink to={`/${docType}/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>← Edytuj dokument</NavLink>
        ) : (
          <NavLink to="/list" style={{ fontSize: "0.85em", color: "#0369a1" }}>← Lista dokumentów</NavLink>
        )}
        <NavLink to={`/read/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>📖 Czytaj</NavLink>
        {docUrl && (
          <a href={docUrl} target="_blank" rel="noopener noreferrer"
            title="Otwórz oryginalny artykuł — porównaj, czy tekst nie jest obcięty"
            style={{ fontSize: "0.85em", color: "#0369a1" }}>
            🔗 Oryginał
          </a>
        )}
        <button onClick={goToNextDocument} disabled={loadingNextDocument}
          title="Przejdź do kolejnego starszego dokumentu, którego review nie zostało zakończone"
          style={{ padding: "3px 9px", border: "1px solid #bae6fd", borderRadius: 4, background: "#f0f9ff", cursor: "pointer", fontSize: "0.82em", color: "#0369a1", fontWeight: 600 }}>
          {loadingNextDocument ? "Szukam…" : "Następny do analizy →"}
        </button>
        {runMode === "article" && (
          <span
            title={docQuality ? qualityTooltip(docQuality) : "Ocena nie została jeszcze wyliczona dla tego dokumentu"}
            style={{
              fontSize: "0.8em", fontWeight: 700, padding: "2px 9px", borderRadius: 10,
              cursor: "help", ...(docQuality ? qualityColors(docQuality.score) : { background: "#f1f5f9", color: "#64748b" }),
            }}
          >
            ⚖ Staranność: {docQuality ? `${docQuality.score}/100` : "nie oceniono"}
          </span>
        )}
        {runMode === "article" && selectedRun !== null && (
          <button onClick={computeQuality} disabled={computingQuality}
            title="Policz ocenę staranności artykułu (kary deterministyczne + rubryka LLM) na chunkach wybranego runu"
            style={{ padding: "2px 9px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.8em", color: "#64748b" }}>
            {computingQuality ? "⚖ Oceniam…" : docQuality ? "⚖ Oceń ponownie" : "⚖ Oceń staranność"}
          </button>
        )}
        <button onClick={reportExtractionIssue} disabled={reportingIssue}
          title="Artykuł błędnie obcięty względem oryginału — odeślij dokument do kolejki ręcznej analizy (NEED_MANUAL_REVIEW + ARTICLE_TRUNCATED)"
          style={{ padding: "2px 9px", border: "1px solid #fca5a5", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.8em", color: "#b91c1c" }}>
          {reportingIssue ? "⚠ Zgłaszam…" : "⚠ Błędnie obcięty"}
        </button>
        <div style={{ marginLeft: "auto" }}><ReaderIdentityBadge identity={identity} /></div>
      </div>

      <div style={{ margin: "16px 0", padding: "12px 16px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "0.86em", color: "#475569" }}>
            {newMode === "article" ? "Artykuł" : "Transkrypcja"}
            {" · "}{newModel}
            {splitPreview && (
              <>
                {` · około ${splitPreview.count} ${splitPreview.count === 1 ? "chunk" : "chunków"}`}
                {` (${splitPreview.length.toLocaleString("pl")} zn.)`}
              </>
            )}
            {newMode === "article" && preclean && !splitOnly && (
              <>
                {" · "}
                <span
                  title="Osobny wstępny krok LLM: zanim tekst zostanie podzielony na chunki do recenzji, model oznacza dokładne zakresy reklam i szumu (np. nawigacja, stopka). Propozycja czyszczenia trafia do tego samego runu do zatwierdzenia przed docelowym podziałem."
                  style={{ borderBottom: "1px dotted #94a3b8", cursor: "help" }}
                >
                  wykrywanie reklam i szumu
                </span>
              </>
            )}
          </span>
          {runs.length > 0 && <button className="button" onClick={() => startAnalysis()} disabled={!!jobId}
            title={hasActiveRun ? "Uruchamia dodatkowy, osobny run — nie kontynuuje istniejącej analizy poniżej. Aby ją kontynuować, użyj przycisku w panelu procesu po prawej." : undefined}
            style={{ marginLeft: "auto", fontWeight: 700, padding: "6px 12px" }}>
            {jobId ? `Analiza… (${jobStatus})` : hasActiveRun ? "+ Nowa analiza" : "▶ Rozpocznij analizę"}
          </button>}
        </div>
        {newMode === "article" && (
          <div style={{ marginTop: 10, padding: "9px 11px", background: "#fff", border: "1px solid #dbeafe", borderRadius: 6 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <strong style={{ fontSize: "0.84em", color: "#334155" }}>1. Kontrola tekstu i podział</strong>
              <button className="button" onClick={prepareSplit} disabled={recleaning || !!jobId || !recleanPreview}
                title="Utwórz nowy run tylko-podział; jeśli cleaner wykrył różnice, najpierw pokaże podsumowanie i poprosi o potwierdzenie">
                {recleaning ? "Przygotowuję…" : recleanPreview ? prepareButtonLabel : "Sprawdzam tekst…"}
              </button>
              {recleanPreview && <span style={{
                fontSize: "0.78em", fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                color: useRecleaned ? "#1e40af" : cleanupNeeded ? "#92400e" : "#166534",
                background: useRecleaned ? "#dbeafe" : cleanupNeeded ? "#fef3c7" : "#dcfce7",
              }}>{useRecleaned ? "widok po czyszczeniu — użyty do podziału" : cleanupNeeded ? "wykryto elementy do czyszczenia" : "tekst nie wymaga ponownego czyszczenia"}</span>}
            </div>
            {recleanPreview && !recleanPreview.portal && (
              <div style={{
                marginTop: 8, fontSize: "0.8em", padding: "6px 9px", borderRadius: 6,
                color: "#92400e", background: "#fef3c7", border: "1px solid #fde68a",
              }}>
                ⚠ Brak reguł czyszczenia dla tego portalu — działa tylko czyszczenie generyczne,
                nawigacja, komentarze, notowania czy sekcje rekomendacji mogą zostać w tekście.
              </div>
            )}
            {recleanPreview && recleanPreview.site_rules_file && !recleanPreview.site_rules_file.ok && (
              <div style={{
                marginTop: 8, fontSize: "0.8em", padding: "6px 9px", borderRadius: 6,
                color: "#991b1b", background: "#fee2e2", border: "1px solid #fecaca",
              }}>
                ⚠ Błąd konfiguracji środowiska: plik reguł czyszczenia (<code>{recleanPreview.site_rules_file.path}</code>)
                {recleanPreview.site_rules_file.reason === "missing" ? " nie istnieje na tym serwerze" : " jest pusty lub uszkodzony na tym serwerze"} —
                jest w repozytorium/GitHub, ale nie w działającym środowisku. Czyszczenie przy pobieraniu dokumentu
                mogło nic nie usunąć niezależnie od reguł per-portal powyżej.
              </div>
            )}
            {recleanPreview && (
              <div style={{ marginTop: 8, fontSize: "0.8em", color: "#475569" }}>
                <div>
                  {useRecleaned ? "Tekst po czyszczeniu" : "Tekst źródłowy"}: <strong>{(useRecleaned ? recleanPreview.after_length : recleanPreview.before_length).toLocaleString("pl")}</strong> znaków,
                  przewidywany podział: <strong>{splitPreview?.count ?? "…"}</strong> {splitPreview?.count === 1 ? "chunk" : "chunków"}.
                  {cleanupNeeded && <> Cleaner zmieni {recleanPreview.removed_line_count} linii
                    {cleanupSignals.length > 0 && <> ({cleanupSignals.join(", ")})</>}.</>}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 8, marginTop: 8 }}>
                  <div>
                    <div style={{ fontWeight: 700, marginBottom: 3, color: "#64748b" }}>Początek {useRecleaned ? "po czyszczeniu" : "tekstu"}</div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto", background: "#f8fafc", padding: 8, borderRadius: 4 }}>
                      {useRecleaned ? recleanPreview.start_preview : recleanPreview.before_start_preview}
                    </pre>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, marginBottom: 3, color: "#64748b" }}>Koniec {useRecleaned ? "po czyszczeniu" : "tekstu"}</div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto", background: "#f8fafc", padding: 8, borderRadius: 4 }}>
                      {useRecleaned ? recleanPreview.end_preview : recleanPreview.before_end_preview}
                    </pre>
                  </div>
                </div>
                {cleanupNeeded && !useRecleaned && <details style={{ marginTop: 5 }}>
                  <summary style={{ cursor: "pointer" }}>Podejrzyj koniec po czyszczeniu</summary>
                  <pre style={{ whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto", background: "#f8fafc", padding: 8, borderRadius: 4 }}>
                    {recleanPreview.end_preview}
                  </pre>
                </details>}
              </div>
            )}
          </div>
        )}
        <details style={{ marginTop: 9 }}>
          <summary style={{ cursor: "pointer", color: "#64748b", fontSize: "0.82em", userSelect: "none" }}>
            Ustawienia zaawansowane
          </summary>
          <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap", alignItems: "center", paddingTop: 8, borderTop: "1px solid #e2e8f0" }}>
          <select value={newModel} onChange={e => setNewModel(e.target.value)} style={{ padding: "4px 8px", fontSize: "0.88em" }}>
            {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={newMode} onChange={e => setNewMode(e.target.value)} style={{ padding: "4px 8px", fontSize: "0.88em" }}
            title="transkrypcja: mówcy + korekta STT; artykuł: czysty tekst, podział po nagłówkach, bez korekty">
            <option value="transcript">transkrypcja (YouTube)</option>
            <option value="article">artykuł (czysty tekst)</option>
          </select>
          {newMode === "article" && chapters.length > 0 && (
            <select value={scopeChapter} style={{ padding: "4px 8px", fontSize: "0.88em", maxWidth: 280 }}
              onChange={e => setScopeChapter(e.target.value === "" ? "" : Number(e.target.value))}
              title="Analizuj cały dokument albo tylko wybrany rozdział (spis treści z nagłówków markdown)">
              <option value="">cały dokument ({chapters.length} rozdz.)</option>
              {chapters.map(c => (
                <option key={c.position} value={c.position}>
                  {c.title} ({(c.length / 1000).toFixed(1)} tys. zn)
                </option>
              ))}
            </select>
          )}
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
          {newMode === "article" && !splitOnly && (
            <label style={{ fontSize: "0.85em", display: "flex", alignItems: "center", gap: 4 }}
              title="LLM najpierw oznaczy dokładne zakresy reklam i szumu. Propozycja oraz docelowy podział zostaną zapisane w jednym runie.">
              <input type="checkbox" checked={preclean} onChange={e => setPreclean(e.target.checked)} />
              najpierw wykryj reklamy i szum
            </label>
          )}
          {splitPreview && (
            <span style={{ fontSize: "0.82em", color: "#475569" }}
              title={`Rozmiary chunków: ${splitPreview.sizes.join(", ")} znaków`}>
              → podział da <strong>{splitPreview.count}</strong> {splitPreview.count === 1 ? "chunk" : "chunki(-ów)"}
              {" "}({splitPreview.length.toLocaleString("pl")} zn
              {splitPreview.count > 1 && `: ${splitPreview.sizes.slice(0, 6).join(" + ")}${splitPreview.sizes.length > 6 ? " + …" : ""}`})
            </span>
          )}
          <button className="button" onClick={() => startAnalysis()} disabled={!!jobId}>
            {jobId ? `Analiza… (${jobStatus})` : hasActiveRun ? "+ Nowa analiza z tymi ustawieniami" : "▶ Rozpocznij analizę z tymi ustawieniami"}
          </button>
          </div>
        </details>
      </div>

      {/* Wybór runu */}
      {runs.length > 0 && (
        <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
          <label style={{ fontSize: "0.85em", fontWeight: 600 }}>Analiza: </label>
          {runs.length > 1 ? (
            <select value={selectedRun ?? ""} onChange={e => setSelectedRun(Number(e.target.value))} style={{ padding: "4px 8px", fontSize: "0.88em" }}>
              {runs.map(r => (
                <option key={r.id} value={r.id}>{runLabelText(r)}</option>
              ))}
            </select>
          ) : (
            <span style={{ fontSize: "0.88em" }}>{runLabelText(runs[0])}</span>
          )}
          <button onClick={deleteRun} title="Usuń wybrany run (chunki i sekcje)"
            style={{ padding: "3px 9px", border: "1px solid #fca5a5", borderRadius: 4, background: "#fff", color: "#b91c1c", cursor: "pointer", fontSize: "0.82em" }}>
            🗑 Usuń run
          </button>
          {false && selectedRun !== null && (runStatus === "reviewed" ? (
            <button onClick={() => setRunWorkflowStatus("in_review")}
              title="Analiza jest zamknięta — otwórz ją ponownie do przeglądu"
              style={{ padding: "3px 9px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#f1f5f9", color: "#475569", cursor: "pointer", fontSize: "0.82em" }}>
              ↺ Otwórz ponownie
            </button>
          ) : (
            <button onClick={() => setRunWorkflowStatus("reviewed")}
              title="Oznacz review tej analizy jako zakończony (status: zamknięta)"
              style={{ padding: "3px 9px", border: "none", borderRadius: 4, background: "#15803d", color: "#fff", cursor: "pointer", fontSize: "0.82em", fontWeight: "bold" }}>
              ✔ Zamknij review
            </button>
          ))}
          {false && runStatus === "reviewed" && (
            <span style={{ fontSize: "0.8em", color: "#15803d", fontWeight: 600 }}>zamknięta</span>
          )}
        </div>
      )}

      {/* Tagi dokumentu (tematyczne + kraje) */}
      {/* Guided workflow: keep the next action in one predictable place. */}
      {selectedRun !== null && (
        <aside className="chunks-workflow" style={{
          marginBottom: 14, padding: "14px 16px", border: "1px solid #cbd5e1",
          borderRadius: 10, background: "#fff", boxShadow: "0 1px 3px rgba(15, 23, 42, .06)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
            <strong style={{ color: "#0f172a" }}>Proces</strong>
            <span style={{ fontSize: "0.82em", color: "#64748b" }}>run #{selectedRun}</span>
            {workflowBusy && <span style={{ fontSize: "0.82em", color: "#0369a1" }}>Przetwarzanie…</span>}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8 }}>
            {([
              {
                label: "1. Analiza chunków",
                done: chunksToAnalyze.length === 0,
                detail: chunksToAnalyze.length > 0 ? `${chunksToAnalyze.length} wymaga analizy` : `${tematChunks.length} treści TEMAT`,
                subs: [
                  {
                    label: "Podział na chunki",
                    done: chunkTotal > 0,
                    detail: chunkTotal > 0 ? `${chunkTotal} chunków` : "brak chunków",
                  },
                  ...(runMode === "article" ? [{
                    label: "Wykrywanie reklam i szumu",
                    done: noiseMarkingDone,
                    detail: reklamaCount > 0 ? `${reklamaCount} poza TEMAT` : noiseMarkingDone ? "nie wykryto" : "oczekuje",
                  }] : []),
                  {
                    label: "Analiza LLM (tematy i streszczenia)",
                    done: tematChunks.length > 0 && chunksToAnalyze.length === 0 && analyzedTematCount > 0,
                    detail: `${analyzedTematCount}/${tematChunks.length} przeanalizowanych`,
                  },
                ],
              },
              {
                label: "2. Przegląd i akceptacja",
                done: reviewReady || runStatus === "reviewed",
                detail: `${approvedCount}/${tematChunks.length} zatwierdzonych`,
                subs: [
                  {
                    label: "Zatwierdzenie chunków TEMAT",
                    done: tematChunks.length > 0 && unapprovedTematCount === 0,
                    detail: `${approvedCount}/${tematChunks.length}`,
                  },
                  {
                    label: "Zamknięcie review",
                    done: runStatus === "reviewed",
                    detail: RUN_STATUS_LABELS[runStatus] ?? runStatus,
                  },
                ],
              },
              {
                label: "3. Embeddingi",
                done: runStatus === "reviewed" && embeddedCount > 0 && !embedJobId,
                detail: embedJobId ? `generowanie: ${embedJobStatus}` : embeddedCount > 0 ? `${embeddedCount} chunków w indeksie` : "uruchomią się po zamknięciu",
                subs: [
                  {
                    label: "Generowanie embeddingów",
                    done: embeddedCount > 0 && !embedJobId,
                    detail: embedJobId ? `w toku: ${embedJobStatus}` : `${embeddedCount}/${approvedCount} zatwierdzonych w indeksie`,
                  },
                ],
              },
            ] as { label: string; done: boolean; detail: string; subs: { label: string; done: boolean; detail: string }[] }[]).map(step => (
              <div key={step.label} style={{
                padding: "10px 12px", borderRadius: 7,
                border: `1px solid ${step.done ? "#86efac" : "#e2e8f0"}`,
                background: step.done ? "#f0fdf4" : "#f8fafc",
              }}>
                <div style={{ fontSize: "0.84em", fontWeight: 700, color: step.done ? "#15803d" : "#334155" }}>
                  {step.done ? "✓ " : ""}{step.label}
                </div>
                <div style={{ marginTop: 3, fontSize: "0.78em", color: "#64748b" }}>{step.detail}</div>
                <div style={{ marginTop: 6, display: "grid", gap: 3, paddingLeft: 2 }}>
                  {step.subs.map(sub => (
                    <div key={sub.label} style={{ display: "flex", gap: 6, fontSize: "0.76em", alignItems: "baseline" }}>
                      <span style={{ color: sub.done ? "#15803d" : "#94a3b8", fontWeight: 700, minWidth: 11 }}>
                        {sub.done ? "✓" : "○"}
                      </span>
                      <span style={{ color: sub.done ? "#15803d" : "#475569" }}>{sub.label}</span>
                      <span style={{ color: "#94a3b8", whiteSpace: "nowrap" }}>— {sub.detail}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch", gap: 8, marginTop: 12 }}>
            {chunksToAnalyze.length > 0 && runStatus !== "reviewed" ? (
              <button className="button" onClick={reanalyzeAll} disabled={reanalyzingAll}
                style={{ background: "#0369a1", color: "#fff", border: "none", fontWeight: 700 }}>
                {reanalyzingAll ? "Analizuję…" : `Dalej: analizuj chunki (${chunksToAnalyze.length})`}
              </button>
            ) : unapprovedTematCount > 0 && runStatus !== "reviewed" ? (
              <button className="button" onClick={approveAll} disabled={workflowBusy}
                style={{ background: "#15803d", color: "#fff", border: "none", fontWeight: 700 }}>
                {approvingAll ? "Zatwierdzam…" : `Dalej: zatwierdź wszystkie TEMAT (${unapprovedTematCount})`}
              </button>
            ) : runStatus !== "reviewed" ? (
              <button className="button" onClick={() => setRunWorkflowStatus("reviewed")} disabled={!reviewReady || workflowBusy}
                title={!reviewReady ? "Najpierw przeanalizuj i zatwierdź wszystkie chunki TEMAT" : "Zamknij review i automatycznie utwórz embeddingi"}
                style={{ background: reviewReady ? "#7c3aed" : "#cbd5e1", color: "#fff", border: "none", fontWeight: 700 }}>
                Zakończ review i utwórz embeddingi
              </button>
            ) : embedJobId ? (
              <span style={{ color: "#0369a1", fontSize: "0.88em", fontWeight: 700 }}>
                Tworzenie embeddingów… ({embedJobStatus})
              </span>
            ) : embeddedCount > 0 ? (
              <span style={{ color: "#15803d", fontSize: "0.88em", fontWeight: 700 }}>✓ Proces zakończony</span>
            ) : (
              <span style={{ color: "#b45309", fontSize: "0.84em", fontWeight: 700 }}>
                Review zakończone, ale brak embeddingów
              </span>
            )}
            {runStatus === "reviewed" && (
              <>
                <button onClick={() => setRunWorkflowStatus("in_review")} disabled={!!embedJobId}
                  style={{ padding: "4px 10px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", color: "#475569", cursor: "pointer", fontSize: "0.82em" }}>
                  ↻ Otwórz review
                </button>
                <button onClick={generateEmbeddings} disabled={!!embedJobId || approvedCount === 0}
                  title="Ręcznie odśwież embeddingi po późniejszych zmianach"
                  style={{ padding: "4px 10px", border: "1px solid #a5f3fc", borderRadius: 4, background: "#ecfeff", color: "#0e7490", cursor: "pointer", fontSize: "0.82em" }}>
                  {embedJobId ? `Odświeżam… (${embedJobStatus})` : "Odśwież embeddingi"}
                </button>
              </>
            )}
            <button className="button" onClick={goToNextDocument} disabled={loadingNextDocument}
              title="Pomiń bieżący dokument i przejdź do kolejnego z niezakończonym review"
              style={{ marginTop: 4, background: "#0369a1", color: "#fff", border: "none", fontWeight: 700, padding: "7px 12px" }}>
              {loadingNextDocument ? "Szukam następnego dokumentu…" : "Następny dokument do sprawdzenia →"}
            </button>
            <span style={{ fontSize: "0.78em", color: "#64748b", lineHeight: 1.4 }}>
              Reklamy i szum są pomijane. Każdy chunk możesz zatwierdzić osobno poniżej.
            </span>
          </div>
        </aside>
      )}

      {(docThematicTags.length > 0 || docCountries.length > 0) && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", border: "1px solid #e2e8f0", borderRadius: 8,
          display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6,
        }}>
          <span style={{ fontWeight: 600, fontSize: "0.85em", color: "#64748b", marginRight: 4 }}>🏷️ Tagi:</span>
          {docThematicTags.map(tag => (
            <span key={tag} style={{
              fontSize: "0.78em", padding: "2px 8px", borderRadius: 999, background: "#f1f5f9", color: "#334155",
            }}>
              {tag}
            </span>
          ))}
          {docCountries.map(c => (
            <span key={c.slug} style={{
              fontSize: "0.78em", padding: "2px 8px", borderRadius: 999, background: "#e0f2fe", color: "#334155",
            }}>
              {c.name_pl}
            </span>
          ))}
        </div>
      )}

      {/* Synteza runu — zwijany panel */}
      {synthesis && (
        <div style={{ marginBottom: 12, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
          <div
            onClick={() => setSynthesisOpen(o => !o)}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", background: "#f8fafc", cursor: "pointer" }}
          >
            <span style={{ color: "#64748b" }}>{synthesisOpen ? "▾" : "▸"}</span>
            <span style={{ fontWeight: 600, fontSize: "0.85em" }}>Synteza</span>
          </div>
          {synthesisOpen && (
            <div style={{ padding: "10px 14px", fontSize: "0.88em", whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
              {synthesis}
            </div>
          )}
        </div>
      )}

      {processComplete && (
        <div style={{
          marginBottom: 14, padding: "18px 20px", border: "1px solid #86efac",
          borderRadius: 10, background: "#f0fdf4",
        }}>
          <div style={{ fontSize: "1.05em", fontWeight: 800, color: "#166534" }}>
            ✓ Proces zakończony — dokument znajduje się w indeksie
          </div>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 9, color: "#475569", fontSize: "0.86em" }}>
            <span><strong>{embeddedCount}</strong> chunków TEMAT z embeddingami</span>
            <span><strong>{approvedCount}</strong> zatwierdzonych</span>
            <span><strong>{reklamaCount}</strong> poza TEMAT pominiętych</span>
            <span>run <strong>#{selectedRun}</strong></span>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 13 }}>
            <NavLink to={`/read/${id}`} className="button" style={{ textDecoration: "none" }}>📖 Czytaj dokument</NavLink>
            <button className="button" onClick={() => setShowCompletedResult(value => !value)}>
              {showCompletedResult ? "Ukryj wynikowe chunki" : "Pokaż wynikowe chunki"}
            </button>
          </div>
          {showCompletedResult && (
            <div style={{ display: "grid", gap: 8, marginTop: 14 }}>
              {tematChunks.map(chunk => (
                <div key={chunk.id} style={{ padding: "10px 12px", border: "1px solid #bbf7d0", borderRadius: 6, background: "#fff" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 5 }}>
                    <strong style={{ color: "#334155" }}>#{chunk.position} {chunk.topic || "TEMAT"}</strong>
                    <span style={{ color: "#15803d", fontSize: "0.78em" }}>● w indeksie</span>
                  </div>
                  <div style={{ whiteSpace: "pre-wrap", color: "#475569", fontSize: "0.84em", lineHeight: 1.5 }}>
                    {(chunk.corrected_text || chunk.original_text || chunk.text_preview || "").slice(0, 700)}
                    {(chunk.text_length ?? (chunk.corrected_text || chunk.original_text || "").length) > 700 ? "…" : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!processComplete && chunks.length > 0 && (
        <div style={{ marginBottom: 12, padding: "8px 14px", background: "#0f172a", borderRadius: 6, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ color: "#94a3b8", fontSize: "0.82em" }}>
            TEMAT: {approvedCount}/{tematChunks.length} zatwierdzonych ({pct}%)
            {reklamaCount > 0 && ` • ${reklamaCount} poza TEMAT${hideAds ? " (ukryte)" : ""}`}
          </span>
          <div style={{ flex: 1, minWidth: 80, background: "#334155", borderRadius: 4, height: 8 }}>
            <div style={{ width: `${pct}%`, height: 8, background: "#22c55e", borderRadius: 4, transition: "width .3s" }} />
          </div>
          {false && unapprovedTematCount > 0 && (
            <button className="button" onClick={approveAll} disabled={approvingAll}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#15803d", color: "#fff", border: "none" }}>
              {approvingAll ? "Zatwierdzam…" : `Zatwierdź wszystkie (${unapprovedTematCount})`}
            </button>
          )}
          {false && chunksToAnalyze.length > 0 && (
            <button className="button" onClick={reanalyzeAll} disabled={reanalyzingAll}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#0369a1", color: "#fff", border: "none" }}>
              {reanalyzingAll ? "Analizuję…" : `Analizuj chunki (${chunksToAnalyze.length})`}
            </button>
          )}
          {reklamaCount > 0 && (visibleReklamaCount > 0 || hideAds) && (
            <button className="button" onClick={() => setHideAds(h => !h)}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: hideAds ? "#475569" : "#b91c1c", color: "#fff", border: "none" }}>
              {hideAds ? `Pokaż fragmenty poza TEMAT (${reklamaCount})` : `Ukryj fragmenty poza TEMAT (${visibleReklamaCount})`}
            </button>
          )}
          {hiddenChunks.size > 0 && (
            <button className="button" onClick={() => setHiddenChunks(new Set())}
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#0369a1", color: "#fff", border: "none" }}>
              Pokaż ukryte ({hiddenChunks.size})
            </button>
          )}
          {visibleMarkedLineCount > 0 && (
            <button className="button" onClick={saveAllVisibleLineRemovals}
              title="Usuń zaznaczone linie ze wszystkich obecnie widocznych chunków i z dokumentu źródłowego"
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#b91c1c", color: "#fff", border: "none" }}>
              Usuń zaznaczone we wszystkich widocznych ({visibleMarkedLineCount})
            </button>
          )}
          <label style={{ fontSize: "0.8em", color: "#94a3b8", display: "flex", alignItems: "center", gap: 4 }}
            title="Pokaż tylko chunki TEMAT bez notatki Obsidian">
            <input type="checkbox" checked={filterUnprocessed} onChange={e => setFilterUnprocessed(e.target.checked)} />
            tylko nieopracowane
          </label>
          {sectionView && (
            <button className="button" onClick={switchToFlatFull}
              title="Wczytaj wszystkie chunki i pokaż je jako jedną listę (bez accordionu sekcji)"
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#475569", color: "#fff", border: "none" }}>
              Widok płaski
            </button>
          )}
          {!sectionView && topicSections.length > 0 && chunkTotal > SECTION_VIEW_THRESHOLD && (
            <button className="button" onClick={() => selectedRun !== null && fetchChunks(selectedRun)}
              title="Wróć do widoku sekcji z lazy-loadingiem chunków"
              style={{ fontSize: "0.8em", padding: "3px 10px", background: "#475569", color: "#fff", border: "none" }}>
              Widok sekcji
            </button>
          )}
        </div>
      )}

      {/* Pasek rozmówców (tylko transkrypcje — artykuły nie mają mówców).
          Gated on !error too: on a failed fetchChunks() runMode keeps its
          stale/default value (the catch block never reaches setRunMode), so
          without this an error banner could still show the transcript-only bar. */}
      {!processComplete && selectedRun !== null && !error && runMode !== "article" && (
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

      {/* Destructive source cleanup is optional, not part of the standard flow. */}
      {runMode === "article" && runStatus !== "reviewed" && chunksToAnalyze.length > 0 && reklamaCount > 0 && (
        <details style={{ marginBottom: 12, padding: "8px 12px", border: "1px solid #e2e8f0", borderRadius: 6, background: "#f8fafc" }}>
          <summary style={{ cursor: "pointer", color: "#64748b", fontSize: "0.82em", userSelect: "none" }}>
            Operacje zaawansowane
          </summary>
          <div style={{ marginTop: 9 }}>
            <button className="button" onClick={applyCleanupAndResplit} disabled={applyingCleanup || workflowBusy}
              title="Trwale nadpisuje tekst źródłowy treścią chunków TEMAT i ŹRÓDŁA, usuwa REKLAMA/SZUM i tworzy nowy run"
              style={{ fontSize: "0.82em", background: "#7c3aed", color: "#fff", border: "none", padding: "5px 10px" }}>
              {applyingCleanup ? "Stosuję czyszczenie…" : "Zastosuj czyszczenie do tekstu źródłowego i utwórz nowy run"}
            </button>
            <p style={{ margin: "7px 0 0", color: "#64748b", fontSize: "0.76em", lineHeight: 1.4 }}>
              Opcjonalne: trwale usuwa odrzucone fragmenty z dokumentu. Standardowy flow nie wymaga tej operacji.
            </p>
          </div>
        </details>
      )}

      {/* Chunki — widok płaski */}
      {!processComplete && !sectionView && visibleChunks.map(renderChunkCard)}

      {/* Doładowanie kolejnej strony (duży run bez sekcji) */}
      {!processComplete && !sectionView && flatPaged && chunks.length < chunkTotal && (
        <div style={{ textAlign: "center", margin: "12px 0" }}>
          <button className="button" onClick={loadMoreChunks} disabled={loadingMore}>
            {loadingMore ? "Ładuję…" : `Załaduj więcej (${chunks.length}/${chunkTotal})`}
          </button>
        </div>
      )}

      {/* Widok sekcji (książki): accordion z lazy-loadingiem chunków */}
      {!processComplete && sectionView && topicSections.map(ts => {
        const expanded = expandedSections.has(ts.id);
        const secLoading = loadingSections[ts.id] ?? false;
        const positions = new Set(ts.chunk_positions);
        const secChunks = visibleChunks.filter(c => positions.has(c.position));
        const pct = ts.temat_count ? Math.round(ts.approved_count / ts.temat_count * 100) : 0;
        const isEditing = editingSectionId === ts.id;
        return (
          <div key={ts.id} style={{ marginBottom: 10, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
            <div
              onClick={() => { if (!isEditing) toggleSection(ts); }}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "#f8fafc", cursor: isEditing ? "default" : "pointer", flexWrap: "wrap" }}
            >
              <span style={{ color: "#64748b" }}>{expanded ? "▾" : "▸"}</span>
              <span style={{ padding: "1px 8px", borderRadius: 4, fontWeight: 600, fontSize: "0.78em", ...typeColor(ts.type) }}>{ts.type}</span>
              {isEditing ? (
                <>
                  <input
                    value={sectionTitleEdits[ts.id] ?? ""}
                    onChange={e => setSectionTitleEdits(prev => ({ ...prev, [ts.id]: e.target.value }))}
                    onClick={e => e.stopPropagation()}
                    onKeyDown={e => { if (e.key === "Enter") saveSectionTitle(ts.id); if (e.key === "Escape") setEditingSectionId(null); }}
                    autoFocus
                    style={{ flex: 1, minWidth: 160, padding: "3px 6px", fontSize: "0.9em" }}
                  />
                  <button onClick={e => { e.stopPropagation(); saveSectionTitle(ts.id); }} disabled={savingSectionTitle}
                    style={{ padding: "2px 10px", borderRadius: 3, border: "none", background: "#3b82f6", color: "#fff", fontSize: "0.78em", cursor: "pointer", fontWeight: "bold" }}>
                    {savingSectionTitle ? "…" : "Zapisz"}
                  </button>
                  <button onClick={e => { e.stopPropagation(); setEditingSectionId(null); }}
                    style={{ padding: "2px 8px", borderRadius: 3, border: "none", background: "#e2e8f0", color: "#475569", fontSize: "0.78em", cursor: "pointer" }}>
                    Anuluj
                  </button>
                </>
              ) : (
                <>
                  <strong style={{ flex: 1, fontSize: "0.92em" }}>{ts.title || `Sekcja ${ts.position}`}</strong>
                  <button
                    onClick={e => { e.stopPropagation(); setEditingSectionId(ts.id); setSectionTitleEdits(prev => ({ ...prev, [ts.id]: ts.title ?? "" })); }}
                    title="Edytuj tytuł sekcji"
                    style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: "0.8em", color: "#64748b" }}
                  >
                    ✏
                  </button>
                </>
              )}
              <span style={{ fontSize: "0.8em", color: "#64748b" }}>
                ✓ {ts.approved_count}/{ts.temat_count} • {ts.chunk_count} chunków
                {ts.notes_count > 0 && ` • 📝 ${ts.notes_count}`}
              </span>
              <div style={{ width: 90, background: "#e2e8f0", borderRadius: 4, height: 7 }}>
                <div style={{ width: `${pct}%`, height: 7, background: "#22c55e", borderRadius: 4 }} />
              </div>
            </div>
            {expanded && (
              <div style={{ padding: "10px 14px", borderTop: "1px solid #e2e8f0" }}>
                {secLoading && <div className="loader" />}
                {!secLoading && secChunks.map(renderChunkCard)}
                {!secLoading && secChunks.length === 0 && (
                  <p style={{ color: "#94a3b8", fontStyle: "italic", margin: 0 }}>Brak widocznych chunków (sprawdź filtry).</p>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Chunki poza sekcjami (rzadkie — sekcje zwykle pokrywają cały run) */}
      {sectionView && (() => {
        const covered = new Set(topicSections.flatMap(ts => ts.chunk_positions));
        const leftover = chunks.filter(c => !covered.has(c.position)).length;
        return leftover > 0 ? (
          <p style={{ color: "#94a3b8", fontSize: "0.85em" }}>
            {leftover} chunków poza sekcjami — użyj przycisku „Widok płaski”, aby je zobaczyć.
          </p>
        ) : null;
      })()}

      {!loading && chunks.length === 0 && runs.length === 0 && (
        <p style={{ color: "#64748b", fontStyle: "italic" }}>
          Brak przygotowanego podziału. W kroku „1. Kontrola tekstu i podział” sprawdź początek oraz koniec tekstu,
          a następnie kliknij „{prepareButtonLabel}”.
        </p>
      )}

      {/* Popover nowej notatki (zaznaczenie tekstu w treści chunka) */}
      {pendingNote && (
        <NotePopover pending={pendingNote} onSave={saveChunkNote} onCancel={() => setPendingNote(null)} />
      )}
    </div>
  );
};

export default Chunks;
