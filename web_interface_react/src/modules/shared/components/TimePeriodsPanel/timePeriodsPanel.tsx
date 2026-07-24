import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";

export interface TimePeriodItem {
  chapter_position: number | null;
  position: number;
  subject_period_label: string;
  subject_period_start_year: number | null;
  subject_period_end_year: number | null;
  confidence: "high" | "medium" | "low";
  evidence: string | null;
}

interface TimePeriodsPanelProps {
  docId?: string;
  currentChapter: number;
}

const CONFIDENCE_LABELS: Record<TimePeriodItem["confidence"], string> = {
  high: "pewność wysoka",
  medium: "pewność średnia",
  low: "pewność niska",
};

export function formatPeriodYear(year: number): string {
  return year < 0 ? `${-year} p.n.e.` : String(year);
}

export function formatPeriodYears(period: TimePeriodItem): string | null {
  const { subject_period_start_year: start, subject_period_end_year: end } = period;
  if (start == null && end == null) return null;
  if (start != null && end != null) {
    return start === end ? formatPeriodYear(start) : `${formatPeriodYear(start)}–${formatPeriodYear(end)}`;
  }
  return start != null ? `od ${formatPeriodYear(start)}` : `do ${formatPeriodYear(end!)}`;
}

const TimePeriodsPanel: React.FC<TimePeriodsPanelProps> = ({ docId, currentChapter }) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [periods, setPeriods] = React.useState<TimePeriodItem[]>([]);
  const [scopeChapter, setScopeChapter] = React.useState(true);
  // null until refresh_document_periods has run at least once for this
  // document (backend: documents.enrichment_run_at) — tells apart "never
  // analyzed" from "analyzed, genuinely no period classified".
  const [enrichmentRunAt, setEnrichmentRunAt] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!docId) return;
    let cancelled = false;
    setPeriods([]);
    setScopeChapter(true);
    setEnrichmentRunAt(null);
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${docId}/time_periods`, {
          headers: { "x-api-key": apiKey ?? "" },
        });
        const data = await response.json();
        if (!response.ok || (data.status && data.status !== "success")) return;
        if (!cancelled) {
          setPeriods((data.time_periods ?? []) as TimePeriodItem[]);
          setEnrichmentRunAt(data.enrichment_run_at ?? null);
        }
      } catch {
        // periods are optional decoration — a failed fetch just hides the panel
      }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, apiKey, docId]);

  const hasChapterRows = React.useMemo(
    () => periods.some(period => period.chapter_position != null),
    [periods],
  );

  const shownPeriods = React.useMemo(() => {
    if (scopeChapter) {
      // whole-document rows double as the "chapter" view for chapterless documents
      const chapterRows = periods.filter(period => period.chapter_position === currentChapter);
      return chapterRows.length > 0 ? chapterRows : periods.filter(period => period.chapter_position == null);
    }
    const byLabel = new Map<string, TimePeriodItem>();
    periods.forEach(period => {
      const key = period.subject_period_label.toLocaleLowerCase("pl");
      const existing = byLabel.get(key);
      if (!existing) {
        byLabel.set(key, { ...period });
        return;
      }
      if (period.subject_period_start_year != null
        && (existing.subject_period_start_year == null || period.subject_period_start_year < existing.subject_period_start_year)) {
        existing.subject_period_start_year = period.subject_period_start_year;
      }
      if (period.subject_period_end_year != null
        && (existing.subject_period_end_year == null || period.subject_period_end_year > existing.subject_period_end_year)) {
        existing.subject_period_end_year = period.subject_period_end_year;
      }
    });
    return [...byLabel.values()].sort((a, b) =>
      (a.subject_period_start_year ?? Number.MAX_SAFE_INTEGER) - (b.subject_period_start_year ?? Number.MAX_SAFE_INTEGER));
  }, [periods, scopeChapter, currentChapter]);

  if (periods.length === 0) {
    if (enrichmentRunAt) return null; // genuinely analyzed, nothing to show
    return (
      <div style={{
        background: "#f8fafc", border: "1px dashed #cbd5e1", borderRadius: 8,
        padding: 10, marginTop: 12, fontSize: "0.82em", color: "#64748b",
      }}>
        ⏳ ℹ️ Okres treści nie został jeszcze przeanalizowany.
      </div>
    );
  }

  return (
    <div style={{
      background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
      padding: 10, marginTop: 12,
    }}>
      <strong style={{ fontSize: "0.85em", display: "block" }}>⏳ Okres treści</strong>

      {hasChapterRows && (
        <div style={{ fontSize: "0.78em", color: "#64748b", display: "flex", gap: 8, marginTop: 6 }}>
          Zakres:
          {([["bieżący rozdział", true], ["cały dokument", false]] as const).map(([label, value]) => (
            <button
              key={label}
              type="button"
              onClick={() => setScopeChapter(value)}
              style={{
                border: "none", background: "none", cursor: "pointer", padding: 0,
                color: scopeChapter === value ? "#0369a1" : "#94a3b8",
                fontWeight: scopeChapter === value ? 600 : undefined,
                textDecoration: scopeChapter === value ? undefined : "underline",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {shownPeriods.length === 0 ? (
        <div style={{ color: "#94a3b8", fontSize: "0.8em", marginTop: 8 }}>
          Brak określonego okresu dla tego rozdziału.
        </div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
          {shownPeriods.map((period, index) => {
            const years = formatPeriodYears(period);
            const isMain = scopeChapter && index === 0;
            const tooltip = [CONFIDENCE_LABELS[period.confidence], period.evidence ?? undefined]
              .filter(Boolean).join(" — ");
            return (
              <span
                key={`${period.chapter_position}-${period.position}-${period.subject_period_label}`}
                title={tooltip || undefined}
                style={{
                  fontSize: "0.78em", padding: "2px 8px", borderRadius: 999,
                  background: isMain ? "#e0f2fe" : "#f1f5f9",
                  color: isMain ? "#0c4a6e" : "#334155",
                  border: isMain ? "1px solid #bae6fd" : "1px solid transparent",
                }}
              >
                {period.subject_period_label}
                {years && <span style={{ color: "#64748b", marginLeft: 5 }}>{years}</span>}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default TimePeriodsPanel;
