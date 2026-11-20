import React from "react";
import { NavLink } from "react-router-dom";
import CollapsibleSection from "../CollapsibleSection/collapsibleSection";
import SkillCommand from "../SkillCommand";
import {
  FlowReadinessStep,
  FlowStageState,
  YOUTUBE_FLOW_DOC_URL,
  youtubeFlowPosition,
} from "../../utils/youtubeFlow";

interface Props {
  docId: string;
  apiUrl: string;
  apiKey: string;
  transcriptMissing: boolean;
  hasChapters: boolean;
  hasOutline: boolean;
  /** Changing this value reloads the readiness steps (e.g. after a save that may have moved the document on). */
  refreshKey?: string;
}

const STATE_ICON: Record<FlowStageState, string> = { done: "✅", current: "▶️", todo: "⬜", optional: "➖" };
const STATE_COLOR: Record<FlowStageState, string> = {
  done: "#15803d", current: "#0369a1", todo: "#64748b", optional: "#94a3b8",
};

/**
 * "Gdzie jestem w flow pracy z tekstem": the stages of the YouTube text workflow with the current one marked, what the
 * document can do next, and links to the matching sections of the documentation. Read-only: it never runs anything,
 * and the readiness request is optional (a failure only hides the later stages' state).
 */
const YoutubeFlowGuide = ({
  docId, apiUrl, apiKey, transcriptMissing, hasChapters, hasOutline, refreshKey,
}: Props) => {
  const [steps, setSteps] = React.useState<FlowReadinessStep[] | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setSteps(null);
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${docId}/readiness`, { headers: { "x-api-key": apiKey } });
        const data = await response.json();
        if (!cancelled && data?.status === "success" && Array.isArray(data.steps)) setSteps(data.steps);
      } catch { /* The guide still shows the stages it can work out from the editor alone. */ }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, apiKey, docId, refreshKey]);

  const position = youtubeFlowPosition({ docId, transcriptMissing, hasChapters, hasOutline, readiness: steps });
  const currentStage = position.stages.find(stage => stage.id === position.current);

  return (
    <CollapsibleSection
      title="🧭 Gdzie jestem w flow pracy z tekstem"
      summaryExtra={
        <span style={{ fontWeight: "normal", color: "#475569" }}>
          {currentStage ? `— teraz: ${currentStage.label}` : position.readinessKnown ? "— wszystkie etapy wykonane" : ""}
        </span>
      }
    >
      <ol
        aria-label="Etapy flow pracy z tekstem"
        style={{ listStyle: "none", display: "flex", flexWrap: "wrap", gap: "6px 14px", margin: "10px 0", padding: 0 }}
      >
        {position.stages.map(stage => (
          <li key={stage.id} style={{ color: STATE_COLOR[stage.state], fontWeight: stage.state === "current" ? 700 : 400 }}>
            <span aria-hidden="true">{STATE_ICON[stage.state]} </span>
            <a
              href={`${YOUTUBE_FLOW_DOC_URL}#${stage.anchor}`}
              target="_blank" rel="noopener noreferrer"
              title="Opis tego etapu w dokumentacji"
              style={{ color: "inherit" }}
            >
              {stage.label}
            </a>
            {stage.state === "optional" && <span style={{ fontWeight: 400 }}> (opcjonalnie)</span>}
          </li>
        ))}
      </ol>

      {position.next.length > 0 && (
        <div>
          <strong>Co dalej</strong>
          <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
            {position.next.map(step => (
              <li key={step.key} style={{ margin: "4px 0" }}>
                {step.to
                  ? <NavLink to={step.to} style={{ color: "#0369a1" }}>{step.label}</NavLink>
                  : step.label}
                {step.skill && <SkillCommand command={step.skill} />}
                {step.note && <div style={{ color: "#667", fontSize: "0.9em" }}>{step.note}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {position.parallelBranches && (
        <div role="note" style={{ marginTop: 8, color: "#92400e" }}>
          Przegląd osób i miejsc oraz analiza chunków są od siebie niezależne: możesz zacząć od dowolnego.
        </div>
      )}
      <div style={{ marginTop: 10, color: "#475569" }}>
        Kolejność jest podpowiedzią, nie wymogiem. Gdy dokument ma już embeddingi, zmiany granic rozdziałów i
        akapitów są blokowane (409); jak to obejść, opisuje dokumentacja.{" "}
        <a href={YOUTUBE_FLOW_DOC_URL} target="_blank" rel="noopener noreferrer" style={{ color: "#0369a1" }}>
          📖 Pełna mapa flow w dokumentacji
        </a>
      </div>
    </CollapsibleSection>
  );
};

export default YoutubeFlowGuide;
