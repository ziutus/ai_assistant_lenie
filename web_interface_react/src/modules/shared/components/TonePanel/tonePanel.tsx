import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";

export interface ToneItem {
  chapter_position: number | null;
  emotion: string;
  secondary_emotions: string | null;
  sentiment: "pozytywne" | "negatywne" | "neutralne" | "mieszane";
  intensity: "niska" | "średnia" | "wysoka";
  registers: string | null;
  evidence: string | null;
}

interface TonePanelProps {
  docId?: string;
  currentChapter: number;
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

const TonePanel: React.FC<TonePanelProps> = ({ docId, currentChapter }) => {
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
  }, [apiUrl, apiKey, docId]);

  // current chapter's tone; whole-document rows (null chapter) are the fallback
  const tone = React.useMemo(() => {
    return tones.find(item => item.chapter_position === currentChapter)
      ?? tones.find(item => item.chapter_position == null)
      ?? null;
  }, [tones, currentChapter]);

  if (!tone) {
    if (enrichmentRunAt) return null; // genuinely analyzed, nothing to show
    return (
      <div style={{
        background: "#f8fafc", border: "1px dashed #cbd5e1", borderRadius: 8,
        padding: 10, marginTop: 12, fontSize: "0.82em", color: "#64748b",
      }}>
        🎭 ℹ️ Ton dokumentu nie został jeszcze przeanalizowany.
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
    </div>
  );
};

export default TonePanel;
