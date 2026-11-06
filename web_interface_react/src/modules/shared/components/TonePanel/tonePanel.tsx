import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";
import ChapterAnalysisRunner from "../ChapterAnalysisRunner/chapterAnalysisRunner";

export interface ToneItem {
  chapter_position: number | null;
  emotion: string;
  secondary_emotions: string | null;
  sentiment: "pozytywne" | "negatywne" | "neutralne" | "mieszane";
  intensity: "niska" | "średnia" | "wysoka";
  registers: string | null;
  evidence: string | null;
  /** The chapter's tone recomputed without its outlier passages (ToneSpansPanel); null until asked. */
  core_tone?: (Omit<ToneItem, "chapter_position" | "core_tone"> & { excluded: number; model?: string }) | null;
}

interface TonePanelProps {
  docId?: string;
  currentChapter: number;
  /** Bump to reload the stored tones (e.g. after the tone without outliers was stored elsewhere on the page). */
  refreshKey?: number;
}

const SENTIMENT_STYLES: Record<ToneItem["sentiment"], React.CSSProperties> = {
  pozytywne: { background: "#dcfce7", color: "#166534", border: "1px solid #bbf7d0" },
  negatywne: { background: "#fee2e2", color: "#b91c1c", border: "1px solid #fecaca" },
  neutralne: { background: "#f1f5f9", color: "#334155", border: "1px solid transparent" },
  mieszane: { background: "#fef3c7", color: "#b45309", border: "1px solid #fde68a" },
};

const INTENSITY_DOTS: Record<ToneItem["intensity"], string> = {
  niska: "●○○",
  "średnia": "●●○",
  wysoka: "●●●",
};

const TonePanel: React.FC<TonePanelProps> = ({ docId, currentChapter, refreshKey = 0 }) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [tones, setTones] = React.useState<ToneItem[]>([]);
  // null until refresh_document_tones has run at least once for this document
  // (backend: documents.enrichment_run_at) — tells apart "never analyzed"
  // from "analyzed, tones is empty" (which shouldn't normally happen, since
  // every processed chapter always gets exactly one tone row).
  const [enrichmentRunAt, setEnrichmentRunAt] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!docId) return;
    let cancelled = false;
    setTones([]);
    setEnrichmentRunAt(null);
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${docId}/tones`, {
          headers: { "x-api-key": apiKey ?? "" },
        });
        const data = await response.json();
        if (!response.ok || (data.status && data.status !== "success")) return;
        if (!cancelled) {
          setTones((data.tones ?? []) as ToneItem[]);
          setEnrichmentRunAt(data.enrichment_run_at ?? null);
        }
      } catch {
        // tone is optional decoration — a failed fetch just hides the panel
      }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, apiKey, docId, refreshKey]);

  // current chapter's tone; whole-document rows (null chapter) are the fallback
  const tone = React.useMemo(() => {
    return tones.find(item => item.chapter_position === currentChapter)
      ?? tones.find(item => item.chapter_position == null)
      ?? null;
  }, [tones, currentChapter]);

  const runner = docId ? (
    <details style={{ marginTop: 8 }}>
      <summary style={{ cursor: "pointer", fontSize: "0.8em", color: "#64748b" }}>
        {tone ? "Oceń ten rozdział ponownie…" : "Oceń ton tego rozdziału…"}
      </summary>
      <ChapterAnalysisRunner<ToneItem>
        apiUrl={apiUrl}
        apiKey={apiKey}
        docId={docId}
        position={currentChapter}
        endpoint="detect_tone"
        resultKey="tones"
        summary="Ocena tonu"
        buttonLabel="🎭 Oceń ton rozdziału"
        title="Model czyta cały rozdział (długi — we fragmentach) i zastępuje zapisany ton tego rozdziału"
        onResult={(result) => {
          if (result.kept_previous) return;
          setTones((current) => [...current.filter((item) => item.chapter_position !== currentChapter), ...result.items]);
          setEnrichmentRunAt(new Date().toISOString());
        }}
      />
    </details>
  ) : null;

  if (!tone) {
    return (
      <div style={{
        background: "#f8fafc", border: "1px dashed #cbd5e1", borderRadius: 8,
        padding: 10, marginTop: 12, fontSize: "0.82em", color: "#64748b",
      }}>
        {enrichmentRunAt ? "🎭 Brak tonu dla tego rozdziału." : "🎭 ℹ️ Ton dokumentu nie został jeszcze przeanalizowany."}
        {runner}
      </div>
    );
  }

  const registers = (tone.registers ?? "").split(",").map(r => r.trim()).filter(Boolean);
  const secondary = (tone.secondary_emotions ?? "").split(",").map(r => r.trim()).filter(Boolean);

  return (
    <div style={{
      background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
      padding: 10, marginTop: 12,
    }}>
      <strong style={{ fontSize: "0.85em", display: "block" }}>🎭 Ton rozdziału</strong>
      <div
        title={tone.evidence ?? undefined}
        style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8, alignItems: "center" }}
      >
        <span style={{
          fontSize: "0.78em", padding: "2px 8px", borderRadius: 999, fontWeight: 600,
          ...SENTIMENT_STYLES[tone.sentiment],
        }}>
          {tone.emotion}
        </span>
        {secondary.map(emotion => (
          <span key={emotion} style={{
            fontSize: "0.78em", padding: "2px 8px", borderRadius: 999,
            ...SENTIMENT_STYLES[tone.sentiment], fontWeight: 400,
          }}>
            {emotion}
          </span>
        ))}
        {registers.map(register => (
          <span key={register} style={{
            fontSize: "0.78em", padding: "2px 8px", borderRadius: 999,
            background: "transparent", color: "#64748b", border: "1px dashed #cbd5e1",
          }}>
            ✒ {register}
          </span>
        ))}
        <span
          title={`Intensywność: ${tone.intensity}`}
          style={{ fontSize: "0.7em", color: "#94a3b8", letterSpacing: 2 }}
        >
          {INTENSITY_DOTS[tone.intensity] ?? ""}
        </span>
      </div>
      {tone.core_tone && (
        <div
          title={`Ocena po wyłączeniu ${tone.core_tone.excluded} fragm. odstających tonem${tone.core_tone.evidence ? ` — ${tone.core_tone.evidence}` : ""}`}
          style={{ marginTop: 8, fontSize: "0.8em", color: "#475569" }}
        >
          ⚖️ Bez fragmentów odstających ({tone.core_tone.excluded}):{" "}
          <span style={{
            padding: "2px 8px", borderRadius: 999, fontWeight: 600, ...SENTIMENT_STYLES[tone.core_tone.sentiment],
          }}>
            {tone.core_tone.emotion}
          </span>
          <span style={{ marginLeft: 6, color: "#94a3b8", letterSpacing: 2 }}>
            {INTENSITY_DOTS[tone.core_tone.intensity] ?? ""}
          </span>
        </div>
      )}
      {runner}
    </div>
  );
};

export default TonePanel;
