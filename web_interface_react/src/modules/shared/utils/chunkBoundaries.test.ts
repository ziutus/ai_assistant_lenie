import { describe, expect, it } from "vitest";
import { canMergeChunkRanges, canMoveBoundaryTo, chunkLocalSplitLines, computeChunkLineRanges, computeMergedSplitIndex, type ChunkForPreview } from "./chunkBoundaries";

const chunk = (original_text: string, position = 0): ChunkForPreview => ({
  id: position + 1, original_text, position, type: "TEMAT", status: "approved",
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

describe("chunk boundary actions", () => {
  const first = { chunkIndex: 0, startLine: 5, endLine: 7 };
  const next = { chunkIndex: 1, startLine: 8, endLine: 9 };
  const lines = ["intro", "intro", "intro", "intro", "intro", "a", "b", "c", "d", "e"];
  it("offers merge only for contiguous lines and consecutive backend chunks", () => {
    const chunks = [chunk("a", 0), chunk("b", 1), chunk("c", 2)];
    expect(canMergeChunkRanges(first, next, chunks, lines)).toBe(true);
    expect(canMergeChunkRanges(first, undefined, chunks, lines)).toBe(false);
    expect(canMergeChunkRanges(first, { ...next, startLine: 9 }, chunks, lines)).toBe(false);
    expect(canMergeChunkRanges(first, { ...next, chunkIndex: 2 }, chunks, lines)).toBe(false);
    expect(canMergeChunkRanges(first, next, [chunk("a", 0), chunk("b", 2)], lines)).toBe(false);
  });
  it("allows a single empty or whitespace-only line between chunks", () => {
    for (const blank of ["", " \t "]) {
      const documentLines = [...lines.slice(0, 8), blank, ...lines.slice(8)];
      expect(canMergeChunkRanges(first, { ...next, startLine: 9, endLine: 10 },
        [chunk("a\nb\nc", 0), chunk("d\ne", 1)], documentLines)).toBe(true);
    }
  });
  it("rejects a gap containing orphaned non-whitespace content", () => {
    const documentLines = [...lines.slice(0, 8), "", "orphaned content", " \t", ...lines.slice(8)];
    expect(canMergeChunkRanges(first, { ...next, startLine: 11, endLine: 12 },
      [chunk("a\nb\nc", 0), chunk("d\ne", 1)], documentLines)).toBe(false);
  });
  it("allows two consecutive blank lines between chunks", () => {
    const documentLines = [...lines.slice(0, 8), "", " \t ", ...lines.slice(8)];
    expect(canMergeChunkRanges(first, { ...next, startLine: 10, endLine: 11 },
      [chunk("a\nb\nc", 0), chunk("d\ne", 1)], documentLines)).toBe(true);
  });
  it("converts global split points to sorted local indices, excluding the start and outside lines", () => {
    expect(chunkLocalSplitLines(new Set([7, 5, 6, 4, 8]), first)).toEqual([1, 2]);
    expect(chunkLocalSplitLines(new Set(), first)).toEqual([]);
  });
  it("computes the merged split index inside the first chunk", () => {
    expect(computeMergedSplitIndex(6, first, next)).toBe(1);
  });
  it("includes the inserted blank line for targets inside the second chunk", () => {
    expect(computeMergedSplitIndex(8, first, next)).toBe(4);
    expect(computeMergedSplitIndex(9, first, next)).toBe(5);
  });
  it.each([5, 9])("rejects the outer edge %i", line => {
    expect(canMoveBoundaryTo(line, first, next)).toBe(false);
  });
  it.each([6, 8])("allows the line just inside either edge %i", line => {
    expect(canMoveBoundaryTo(line, first, next)).toBe(true);
  });
  it("allows the current boundary", () => {
    expect(canMoveBoundaryTo(next.startLine, first, next)).toBe(true);
  });
  it.each([4, 10])("rejects targets outside the pair %i", line => {
    expect(canMoveBoundaryTo(line, first, next)).toBe(false);
  });
});
