import { describe, expect, it } from "vitest";
import { FlowReadinessStep, youtubeFlowPosition } from "./youtubeFlow";

const steps = (states: Partial<Record<string, FlowReadinessStep["state"]>>): FlowReadinessStep[] =>
  ["content", "chunks", "embeddings", "ner", "enrichment", "tags"].map(key => ({ key, state: states[key] ?? "todo" }));

const base = { docId: "42", transcriptMissing: false, hasChapters: true, hasOutline: false };

describe("youtubeFlowPosition", () => {
  it("points at the import when there is no transcript", () => {
    const position = youtubeFlowPosition({ ...base, transcriptMissing: true, hasChapters: false, readiness: null });
    expect(position.current).toBe("import");
    expect(position.next.map(step => step.key)).toEqual(["captions"]);
    expect(position.stages.find(stage => stage.id === "import")?.state).toBe("current");
  });

  it("offers chapter proposals and the outline skill for a headerless transcript", () => {
    const position = youtubeFlowPosition({
      ...base, hasChapters: false, readiness: steps({ content: "done" }),
    });
    expect(position.current).toBe("structure");
    const keys = position.next.map(step => step.key);
    expect(keys).toContain("chapters-ai");
    expect(keys).toContain("outline");
    expect(position.next.find(step => step.key === "outline")?.skill).toBe("/lenie-youtube-outline 42");
    // NER is still offered: it works without chapters (whole-document view).
    expect(position.next.find(step => step.key === "ner")?.to).toBe("/ner/42");
  });

  it("does not suggest the outline skill when an outline is saved", () => {
    const position = youtubeFlowPosition({
      ...base, hasChapters: false, hasOutline: true, readiness: steps({ content: "done" }),
    });
    expect(position.next.map(step => step.key)).not.toContain("outline");
  });

  it("treats a started analysis as structure done even without headings", () => {
    const position = youtubeFlowPosition({
      ...base, hasChapters: false, readiness: steps({ content: "done", chunks: "partial" }),
    });
    expect(position.stages.find(stage => stage.id === "structure")?.state).toBe("done");
    expect(position.current).toBe("chunks");
    expect(position.next.map(step => step.key)).not.toContain("chapters-ai");
  });

  it("reports both branches as open and links the first NER chapter", () => {
    const position = youtubeFlowPosition({ ...base, readiness: steps({ content: "done" }) });
    expect(position.current).toBe("chunks");
    expect(position.parallelBranches).toBe(true);
    expect(position.next.find(step => step.key === "ner")?.to).toBe("/ner/42/1");
    expect(position.next.find(step => step.key === "chunks")?.to).toBe("/chunks/42");
  });

  it("asks to finish a partly reviewed run rather than start one", () => {
    const position = youtubeFlowPosition({ ...base, readiness: steps({ content: "done", chunks: "partial" }) });
    expect(position.next.find(step => step.key === "chunks")?.label).toBe("Dokończ przegląd chunków");
  });

  it("offers embeddings when the review is closed but no vectors exist", () => {
    const position = youtubeFlowPosition({
      ...base, readiness: steps({ content: "done", chunks: "done", ner: "done" }),
    });
    expect(position.current).toBe("embeddings");
    expect(position.next.map(step => step.key)).toContain("embeddings");
    expect(position.parallelBranches).toBe(false);
  });

  it("offers the per-chapter analyses once entities are reviewed", () => {
    const position = youtubeFlowPosition({
      ...base, readiness: steps({ content: "done", chunks: "done", embeddings: "done", ner: "done" }),
    });
    expect(position.current).toBe("enrichment");
    expect(position.next.find(step => step.key === "enrichment")?.to).toBe("/ner/42/1");
  });

  it("finishes with reading, the registry and the Obsidian skill", () => {
    const position = youtubeFlowPosition({
      ...base,
      readiness: steps({ content: "done", chunks: "done", embeddings: "done", ner: "done", enrichment: "done" }),
    });
    expect(position.current).toBeNull();
    expect(position.next.map(step => step.key)).toEqual(["read", "registries", "obsidian"]);
    expect(position.next.find(step => step.key === "obsidian")?.skill).toBe("/lenie-obsidian-note 42");
    expect(position.stages.filter(stage => stage.state === "done").length).toBe(6);
  });

  it("keeps the optional stages out of the chain", () => {
    const position = youtubeFlowPosition({ ...base, readiness: steps({ content: "done" }) });
    const optional = position.stages.filter(stage => stage.state === "optional").map(stage => stage.id);
    expect(optional).toEqual(["corrections", "registries"]);
  });

  it("degrades gracefully when readiness could not be loaded", () => {
    const position = youtubeFlowPosition({ ...base, readiness: null });
    expect(position.readinessKnown).toBe(false);
    expect(position.parallelBranches).toBe(false);
    expect(position.next.map(step => step.key)).toEqual(["readiness-unknown"]);
    // What the editor alone can tell is still right: import and structure are done.
    expect(position.stages.find(stage => stage.id === "structure")?.state).toBe("done");
  });
});
