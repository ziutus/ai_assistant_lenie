import React from "react";
import { renderInline } from "../../pages/read";

// Obsidian-flavoured Markdown for notes written by hand (tool notes). The reader's
// `renderMarkdown` targets long imported articles (flat lists, no quotes or task
// lists), so this is a separate block parser that covers what an Obsidian note
// actually uses: headings, nested bullet/numbered/task lists, quotes and
// `> [!callouts]`, tables, fenced code, ==highlight== and ~~strikethrough~~. Inline
// bold/italic/code/links/[[wikilinks]] are delegated to the reader's `renderInline`.

type ListItem = { indent: number; ordered: boolean; text: string; checked: boolean | null };
type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "hr" }
  | { kind: "code"; lang: string; content: string }
  | { kind: "quote"; lines: string[] }
  | { kind: "table"; rows: string[][]; aligns: Array<"left" | "center" | "right" | null> }
  | { kind: "list"; items: ListItem[] }
  | { kind: "paragraph"; text: string };

const FENCE_RE = /^\s*(```+|~~~+)\s*([\w+#.-]*)\s*$/;
const HEADING_RE = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const HR_RE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const QUOTE_RE = /^\s*>\s?(.*)$/;
const TABLE_SEPARATOR_RE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

const splitRow = (line: string): string[] =>
  line.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map(cell => cell.trim().replace(/\\\|/g, "|"));

export function parseBlocks(source: string): Block[] {
  // YAML front matter (tags, aliases…) is hidden by Obsidian too (it shows it as "Properties").
  const withoutFrontMatter = source.replace(/^\s*---\n[\s\S]*?\n---[ \t]*(\n|$)/, "");
  const lines = withoutFrontMatter.replace(/\r\n?/g, "\n").replace(/^\t+/gm, tabs => "    ".repeat(tabs.length)).split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") { i++; continue; }

    const fence = line.match(FENCE_RE);
    if (fence) {
      const marker = fence[1][0];
      const body: string[] = [];
      i++;
      while (i < lines.length && !new RegExp(`^\\s*${marker}{${fence[1].length},}\\s*$`).test(lines[i])) body.push(lines[i++]);
      i++; // closing fence (or end of text for an unterminated one)
      blocks.push({ kind: "code", lang: fence[2], content: body.join("\n") });
      continue;
    }

    const heading = line.match(HEADING_RE);
    if (heading) { blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] }); i++; continue; }
    if (HR_RE.test(line)) { blocks.push({ kind: "hr" }); i++; continue; }

    if (QUOTE_RE.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && QUOTE_RE.test(lines[i])) quote.push(lines[i++].match(QUOTE_RE)![1]);
      blocks.push({ kind: "quote", lines: quote });
      continue;
    }

    if (line.includes("|") && i + 1 < lines.length && TABLE_SEPARATOR_RE.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const header = splitRow(line);
      const aligns = splitRow(lines[i + 1]).map(cell => {
        const left = cell.startsWith(":"), right = cell.endsWith(":");
        return left && right ? "center" as const : right ? "right" as const : left ? "left" as const : null;
      });
      const rows = [header];
      i += 2;
      while (i < lines.length && lines[i].trim() !== "" && lines[i].includes("|")) rows.push(splitRow(lines[i++]));
      blocks.push({ kind: "table", rows, aligns });
      continue;
    }

    if (LIST_RE.test(line)) {
      const items: ListItem[] = [];
      while (i < lines.length) {
        const current = lines[i];
        const item = current.match(LIST_RE);
        if (item) {
          const task = item[3].match(/^\[( |x|X)\]\s+(.*)$/);
          items.push({
            indent: item[1].length, ordered: /^\d/.test(item[2]),
            text: task ? task[2] : item[3], checked: task ? task[1] !== " " : null,
          });
          i++;
        } else if (current.trim() === "") {
          // A blank line inside a list only ends it when no list item follows.
          const next = lines.slice(i + 1).find(candidate => candidate.trim() !== "");
          if (next !== undefined && LIST_RE.test(next)) i++; else break;
        } else if (/^\s+\S/.test(current) && items.length) {
          items[items.length - 1].text += `\n${current.trim()}`; // indented continuation of the item
          i++;
        } else break;
      }
      blocks.push({ kind: "list", items });
      continue;
    }

    // Paragraph: runs until a blank line or the start of another block, so a heading or list that
    // follows without a blank line (common in Obsidian) is not swallowed into the paragraph.
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !FENCE_RE.test(lines[i]) && !HEADING_RE.test(lines[i])
      && !HR_RE.test(lines[i]) && !QUOTE_RE.test(lines[i]) && !LIST_RE.test(lines[i])) paragraph.push(lines[i++]);
    blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
  }
  return blocks;
}

const markStyle = { background: "#fef08a", borderRadius: 2, padding: "0 2px" } as const;

function renderRich(text: string): React.ReactNode[] {
  // ==highlight== and ~~strikethrough~~ are not known to renderInline, so split them off first.
  return text.split(/(==[^=\n]+==|~~[^~\n]+~~)/g).flatMap((part, index) => {
    if (/^==[^=]+==$/.test(part)) return [<mark key={index} style={markStyle}>{renderInline(part.slice(2, -2))}</mark>];
    if (/^~~[^~]+~~$/.test(part)) return [<del key={index} style={{ color: "#64748b" }}>{renderInline(part.slice(2, -2))}</del>];
    return part ? [<React.Fragment key={index}>{renderInline(part)}</React.Fragment>] : [];
  });
}

type ListNode = ListItem & { children: ListNode[] };

function buildListTree(items: ListItem[]): ListNode[] {
  const roots: ListNode[] = [];
  const stack: ListNode[] = [];
  items.forEach(item => {
    const node: ListNode = { ...item, children: [] };
    while (stack.length && stack[stack.length - 1].indent >= node.indent) stack.pop();
    (stack.length ? stack[stack.length - 1].children : roots).push(node);
    stack.push(node);
  });
  return roots;
}

function renderListNodes(nodes: ListNode[], key: string): React.ReactNode {
  const Tag = nodes[0]?.ordered ? "ol" : "ul";
  return <Tag key={key} style={{ margin: "6px 0", paddingLeft: 24, lineHeight: 1.6 }}>
    {nodes.map((node, index) => <li key={index} style={node.checked !== null ? { listStyle: "none", marginLeft: -20 } : undefined}>
      {node.checked !== null && <input type="checkbox" checked={node.checked} readOnly aria-label={node.checked ? "zrobione" : "do zrobienia"}
        style={{ marginRight: 6 }} />}
      <span style={{ whiteSpace: "pre-line", ...(node.checked ? { color: "#64748b", textDecoration: "line-through" } : {}) }}>{renderRich(node.text)}</span>
      {node.children.length > 0 && renderListNodes(node.children, `${key}-${index}`)}
    </li>)}
  </Tag>;
}

const CALLOUT_RE = /^\[!(\w+)\][+-]?\s*(.*)$/;
const CALLOUT_COLORS: Record<string, [string, string]> = {
  info: ["#eff6ff", "#3b82f6"], note: ["#eff6ff", "#3b82f6"], abstract: ["#ecfeff", "#06b6d4"], todo: ["#eff6ff", "#3b82f6"],
  tip: ["#ecfdf5", "#10b981"], success: ["#f0fdf4", "#16a34a"], question: ["#fefce8", "#ca8a04"],
  warning: ["#fffbeb", "#f59e0b"], caution: ["#fffbeb", "#f59e0b"], danger: ["#fef2f2", "#dc2626"],
  error: ["#fef2f2", "#dc2626"], bug: ["#fef2f2", "#dc2626"], example: ["#faf5ff", "#9333ea"], quote: ["#f8fafc", "#94a3b8"],
};

function renderBlock(block: Block, key: string): React.ReactNode {
  switch (block.kind) {
    case "heading": {
      // The page already uses h1/h2 for its own title; the note's "#" becomes h3.
      const level = Math.min(block.level + 2, 6);
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      return <Tag key={key} style={{ color: "#0c2f4a", margin: block.level === 1 ? "22px 0 8px" : "18px 0 6px", fontSize: ["1.25rem", "1.1rem", "1rem", "0.95rem"][Math.min(block.level - 1, 3)] }}>
        {renderRich(block.text)}
      </Tag>;
    }
    case "hr":
      return <hr key={key} style={{ margin: "16px 0", border: "none", borderTop: "1px solid #e2e8f0" }} />;
    case "code":
      return <div key={key} style={{ position: "relative", margin: "12px 0" }}>
        {block.lang && <span style={{ position: "absolute", top: 6, right: 10, fontSize: "0.72em", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.04em" }}>{block.lang}</span>}
        <pre style={{ background: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", overflowX: "auto", margin: 0, fontSize: "0.85em", lineHeight: 1.5 }}>
          <code style={{ fontFamily: "monospace", whiteSpace: "pre" }}>{block.content}</code>
        </pre>
      </div>;
    case "quote": {
      const callout = block.lines[0]?.match(CALLOUT_RE);
      if (callout) {
        const type = callout[1].toLowerCase();
        const [background, accent] = CALLOUT_COLORS[type] ?? CALLOUT_COLORS.note;
        return <div key={key} style={{ background, borderLeft: `4px solid ${accent}`, borderRadius: 6, padding: "8px 14px", margin: "12px 0" }}>
          <div style={{ fontWeight: 600, color: accent, textTransform: callout[2] ? undefined : "capitalize" }}>{callout[2] ? renderRich(callout[2]) : type}</div>
          {block.lines.length > 1 && <MarkdownView text={block.lines.slice(1).join("\n")} />}
        </div>;
      }
      return <blockquote key={key} style={{ margin: "12px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 14 }}>
        <MarkdownView text={block.lines.join("\n")} />
      </blockquote>;
    }
    case "table": {
      const [header, ...rows] = block.rows;
      const cell = (text: string, column: number) => ({ textAlign: block.aligns[column] ?? "left", children: renderRich(text) });
      return <div key={key} style={{ overflowX: "auto", margin: "12px 0" }}>
        <table style={{ borderCollapse: "collapse", fontSize: "0.9em" }}>
          <thead><tr>{header.map((text, column) => {
            const { textAlign, children } = cell(text, column);
            return <th key={column} style={{ border: "1px solid #e2e8f0", background: "#f8fafc", padding: "6px 10px", textAlign }}>{children}</th>;
          })}</tr></thead>
          <tbody>{rows.map((row, r) => <tr key={r}>{row.map((text, column) => {
            const { textAlign, children } = cell(text, column);
            return <td key={column} style={{ border: "1px solid #e2e8f0", padding: "6px 10px", textAlign }}>{children}</td>;
          })}</tr>)}</tbody>
        </table>
      </div>;
    }
    case "list":
      return renderListNodes(buildListTree(block.items), key);
    case "paragraph":
      return <p key={key} style={{ margin: "8px 0", lineHeight: 1.65, whiteSpace: "pre-line" }}>{renderRich(block.text)}</p>;
  }
}

export default function MarkdownView({ text }: { text: string }) {
  const blocks = React.useMemo(() => parseBlocks(text), [text]);
  return <div className="markdown-view" style={{ color: "#334155", overflowWrap: "anywhere" }}>
    {blocks.map((block, index) => renderBlock(block, String(index)))}
  </div>;
}
