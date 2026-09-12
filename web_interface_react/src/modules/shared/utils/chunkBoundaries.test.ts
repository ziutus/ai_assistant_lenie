import { describe, expect, it } from "vitest";
import { computeChunkLineRanges, type ChunkForPreview } from "./chunkBoundaries";

const chunk = (original_text: string, position = 0): ChunkForPreview => ({
  original_text, position, type: "TEMAT", status: "approved",
});

describe("computeChunkLineRanges", () => {
  it("matches chunks end-to-end, stripping one trailing newline", () => {
    expect(computeChunkLineRanges(["a", "b", "c", "d"], [chunk("a\nb\n"), chunk("c\nd")])).toEqual([
      { chunkIndex: 0, startLine: 0, endLine: 1 },
      { chunkIndex: 1, startLine: 2, endLine: 3 },
    ]);
  });
  it("skips edited chunks and continues from the same cursor", () => {
    expect(computeChunkLineRanges(["a", "edited", "c"], [chunk("a"), chunk("b"), chunk("c")])).toEqual([
      { chunkIndex: 0, startLine: 0, endLine: 0 },
      { chunkIndex: 2, startLine: 2, endLine: 2 },
    ]);
  });
  it("skips empty and newline-only chunks", () => {
    expect(computeChunkLineRanges(["", "a"], [chunk(""), chunk("\n"), chunk("a")])).toEqual([
      { chunkIndex: 2, startLine: 1, endLine: 1 },
    ]);
  });
  it("never rewinds or sorts input chunks", () => {
    expect(computeChunkLineRanges(["a", "b", "c"], [chunk("b", 2), chunk("a", 1), chunk("c", 3)])).toEqual([
      { chunkIndex: 0, startLine: 1, endLine: 1 },
      { chunkIndex: 2, startLine: 2, endLine: 2 },
    ]);
  });
  it("returns no ranges for no chunks", () => {
    expect(computeChunkLineRanges(["a"], [])).toEqual([]);
  });
  it("matches single-line and multi-line chunks together", () => {
    expect(computeChunkLineRanges(["intro", "a", "b", "c"], [chunk("a"), chunk("b\nc")])).toEqual([
      { chunkIndex: 0, startLine: 1, endLine: 1 },
      { chunkIndex: 1, startLine: 2, endLine: 3 },
    ]);
  });
  it("preserves whitespace and additional trailing blank lines", () => {
    expect(computeChunkLineRanges(["a", " a", "", "b"], [chunk("a\n\n"), chunk(" a\n\n"), chunk("b\r")])).toEqual([
      { chunkIndex: 1, startLine: 1, endLine: 2 },
    ]);
  });
});
