/**
 * Where a YouTube document stands in the text workflow, and what it can do next.
 *
 * The map itself lives in `docs/youtube-text-workflow.md` (the anchors below are explicit `<a id>` tags in that
 * file — keep the two in sync). This module only turns what the editor already knows (is there a transcript, are
 * there `##` chapters) plus the `GET /document/:id/readiness` steps into a list of stages and next actions. It never
 * triggers anything; the order is advice, not a gate (the backend enforces only its 409 guards).
 */

export const YOUTUBE_FLOW_DOC_URL =
  "https://github.com/ziutus/ai_assistant_lenie/blob/main/docs/youtube-text-workflow.md";

export type FlowStageId =
  | "import"
  | "corrections"
  | "structure"
  | "chunks"
  | "embeddings"
  | "entities"
  | "enrichment"
  | "registries";

/** `done` finished, `current` the first unfinished stage of the chain, `todo` still ahead, `optional` has no state. */
export type FlowStageState = "done" | "current" | "todo" | "optional";

export interface FlowStage {
  id: FlowStageId;
  label: string;
  state: FlowStageState;
  /** Fragment of the documentation page this stage is described under. */
  anchor: string;
}

export interface FlowNextStep {
  key: string;
  label: string;
  /** In-app route. */
  to?: string;
  /** Claude Code skill command to copy. */
  skill?: string;
  /** Short explanation shown under the label. */
  note?: string;
}

export interface FlowReadinessStep {
  key: string;
  state: "done" | "partial" | "todo" | "na";
}

export interface FlowInput {
  docId: string;
  transcriptMissing: boolean;
  /** The transcript text has `##` headings. */
  hasChapters: boolean;
  /** `Document.outline_md` is saved. */
  hasOutline: boolean;
  /** `steps` of `GET /document/:id/readiness`, or null when it could not be loaded. */
  readiness: FlowReadinessStep[] | null;
}

export interface FlowPosition {
  stages: FlowStage[];
  current: FlowStageId | null;
  next: FlowNextStep[];
  /** True when both the chunk branch and the entity branch are still open (they are independent). */
  parallelBranches: boolean;
  readinessKnown: boolean;
}

const STAGE_META: Record<FlowStageId, { label: string; anchor: string }> = {
  import: { label: "Import", anchor: "flow-import" },
  corrections: { label: "Poprawki transkrypcji", anchor: "flow-corrections" },
  structure: { label: "Rozdziały i akapity", anchor: "flow-structure" },
  chunks: { label: "Chunki i przegląd", anchor: "flow-chunks" },
  embeddings: { label: "Embeddingi", anchor: "flow-chunks" },
  entities: { label: "Osoby i miejsca (NER)", anchor: "flow-entities" },
  enrichment: { label: "Wzbogacenie rozdziałów", anchor: "flow-enrichment" },
  registries: { label: "Rejestry i notatki", anchor: "flow-enrichment" },
};

const STAGE_ORDER: FlowStageId[] = [
  "import", "corrections", "structure", "chunks", "embeddings", "entities", "enrichment", "registries",
];

/** Stages that have a real, checkable state, in the order the first unfinished one is picked. */
const CHAIN: FlowStageId[] = ["import", "structure", "chunks", "embeddings", "entities", "enrichment"];

export function youtubeFlowPosition(input: FlowInput): FlowPosition {
  const { docId, transcriptMissing, hasChapters, hasOutline, readiness } = input;
  const readinessKnown = readiness !== null;
  const stateOf = (key: string): FlowReadinessStep["state"] | undefined =>
    readiness?.find(step => step.key === key)?.state;

  const chunks = stateOf("chunks");
  const chunksStarted = chunks === "done" || chunks === "partial";
  const done: Record<string, boolean> = {
    import: !transcriptMissing,
    // Chunks can exist without headings (a blind sentence split), so a started analysis also closes this stage.
    structure: !transcriptMissing && (hasChapters || chunksStarted),
    chunks: chunks === "done",
    embeddings: stateOf("embeddings") === "done",
    entities: stateOf("ner") === "done",
    enrichment: stateOf("enrichment") === "done",
  };

  const current = CHAIN.find(id => !done[id]) ?? null;
  const stages: FlowStage[] = STAGE_ORDER.map(id => {
    const optional = id === "corrections" || id === "registries";
    const state: FlowStageState = optional ? "optional" : done[id] ? "done" : id === current ? "current" : "todo";
    return { id, label: STAGE_META[id].label, state, anchor: STAGE_META[id].anchor };
  });

  const ner = hasChapters ? `/ner/${docId}/1` : `/ner/${docId}`;
  const next: FlowNextStep[] = [];

  if (transcriptMissing) {
    next.push({
      key: "captions",
      label: "Pobierz transkrypcję",
      note: "Użyj przycisku w sekcji „Transkrypcja nie jest jeszcze dostępna” poniżej (napisy, a gdy ich brak, płatne STT).",
    });
  } else {
    if (!hasChapters && !chunksStarted) {
      next.push({
        key: "chapters-ai",
        label: "Podziel transkrypcję na rozdziały",
        note: "Sekcja „Podział na rozdziały (AI)” poniżej: model proponuje granice, Ty zatwierdzasz. Bez rozdziałów chunki dzielą się ślepo co ok. 5000 znaków.",
      });
      if (!hasOutline) {
        next.push({
          key: "outline",
          label: "Albo wygeneruj spis treści ze skilla",
          skill: `/lenie-youtube-outline ${docId}`,
          note: "Po zatwierdzeniu spisu użyj „Zastosuj spis treści jako rozdziały”.",
        });
      }
    }
    if (readinessKnown) {
      if (!done.entities) {
        next.push({
          key: "ner",
          label: "Przejrzyj osoby, miejsca i organizacje",
          to: ner,
          note: "Przycisk zapisu w edytorze prowadzi właśnie tutaj; NER czyta tylko rozdziały uznane za treść.",
        });
      }
      if (!done.chunks) {
        next.push({
          key: "chunks",
          label: chunks === "partial" ? "Dokończ przegląd chunków" : "Przeanalizuj i zatwierdź chunki",
          to: `/chunks/${docId}`,
          note: "Model poprawia tekst i streszcza; embeddingi powstają z zatwierdzonych chunków TEMAT po zamknięciu przeglądu.",
        });
      } else if (!done.embeddings) {
        next.push({
          key: "embeddings",
          label: "Wygeneruj embeddingi",
          to: `/chunks/${docId}`,
          note: "Przegląd jest zamknięty, ale nie ma jeszcze wektorów do wyszukiwania.",
        });
      }
      if (done.entities && !done.enrichment) {
        next.push({
          key: "enrichment",
          label: "Uruchom analizy rozdziałów",
          to: ner,
          note: "Zdarzenia z datą, ton, okresy i źródła, osobno dla każdego rozdziału; żadna nie startuje sama.",
        });
      }
      if (CHAIN.every(id => done[id])) {
        next.push({ key: "read", label: "Czytaj dokument", to: `/read/${docId}` });
        next.push({
          key: "registries",
          label: "Dopisz zdarzenia do rejestru świata",
          to: "/world-events",
          note: "Propozycje zdarzeń z rozdziałów promujesz na /ner/:id/:rozdział albo skillem /lenie-chapter-world-events.",
        });
        next.push({ key: "obsidian", label: "Utwórz notatkę Obsidian", skill: `/lenie-obsidian-note ${docId}` });
      }
    } else {
      next.push({
        key: "readiness-unknown",
        label: "Nie udało się wczytać stanu dalszych etapów",
        note: "Otwórz czytnik albo przegląd chunków, żeby sprawdzić, co jest już zrobione.",
        to: `/read/${docId}`,
      });
    }
  }

  return {
    stages,
    current,
    next,
    parallelBranches: readinessKnown && !transcriptMissing && !done.entities && !done.chunks,
    readinessKnown,
  };
}
