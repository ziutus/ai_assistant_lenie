export interface ChunkForPreview {
  position: number;
  type: string;
  status: string;
  original_text: string;
}

export interface ChunkLineRange {
  chunkIndex: number;
  startLine: number;
  endLine: number;
}

export function computeChunkLineRanges(lines: string[], chunks: ChunkForPreview[]): ChunkLineRange[] {
  const ranges: ChunkLineRange[] = [];
  let cursor = 0;
  chunks.forEach((chunk, chunkIndex) => {
    if (!chunk.original_text || chunk.original_text === "\n") return;
    const chunkLines = chunk.original_text.split("\n");
    if (chunkLines[chunkLines.length - 1] === "") chunkLines.pop();
    if (!chunkLines.length) return;
    for (let i = cursor; i + chunkLines.length <= lines.length; i++) {
      if (chunkLines.every((line, offset) => lines[i + offset] === line)) {
        ranges.push({ chunkIndex, startLine: i, endLine: i + chunkLines.length - 1 });
        cursor = i + chunkLines.length;
        break;
      }
    }
  });
  return ranges;
}
