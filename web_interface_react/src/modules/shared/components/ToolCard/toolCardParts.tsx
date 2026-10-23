import React from "react";
import { Link } from "react-router-dom";

// Presentational pieces of a catalog tool card (`/tools`). They only render what the API returned;
// all state and requests stay in the page.

export type ToolLinkItem = { url: string; label: string; kind: "homepage" | "github" | "wikipedia" | "pricing" | "extra" };

type LinkSource = {
  homepage_url: string | null; github_url: string | null; wikipedia_url: string | null; pricing_url: string | null;
  links?: Array<{ url: string; label: string }>;
};

// Every page about the tool in one list: the named fields first, then the extra links (no duplicates).
export const toolLinks = (tool: LinkSource): ToolLinkItem[] => {
  const named: ToolLinkItem[] = [
    { url: tool.homepage_url ?? "", label: "Strona", kind: "homepage" },
    { url: tool.github_url ?? "", label: "GitHub", kind: "github" },
    { url: tool.wikipedia_url ?? "", label: "Wikipedia", kind: "wikipedia" },
    { url: tool.pricing_url ?? "", label: "Cennik", kind: "pricing" },
  ].filter(item => item.url) as ToolLinkItem[];
  const seen = new Set(named.map(item => item.url));
  const extra = (tool.links ?? [])
    .filter(link => link.url && !seen.has(link.url))
    .map(link => ({ url: link.url, label: link.label || hostOf(link.url), kind: "extra" as const }));
  return [...named, ...extra];
};

export const hostOf = (url: string): string => {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: ".72rem", textTransform: "uppercase", letterSpacing: ".05em", color: "#94a3b8", margin: "0 0 4px", fontWeight: 600,
};

export function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return <section style={{ margin: "14px 0 0", paddingTop: 10, borderTop: "1px solid #f1f5f9" }}>
    <h4 style={sectionTitleStyle} title={hint}>{title}</h4>
    {children}
  </section>;
}

export function Chip({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "warn" | "info" }) {
  const colors = {
    neutral: ["#e2e8f0", "#334155"], warn: ["#fef3c7", "#92400e"], info: ["#ecfeff", "#155e75"],
  }[tone];
  return <span style={{ background: colors[0], color: colors[1], borderRadius: 4, padding: "2px 7px", fontSize: ".78rem" }}>{children}</span>;
}

type Fact = [string, React.ReactNode];

// Type, platforms, licence, pricing model/description as a label/value grid instead of "·"-joined strings.
export function ToolFacts({ facts }: { facts: Fact[] }) {
  const shown = facts.filter(([, value]) => value);
  if (!shown.length) return null;
  return <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "8px 18px", margin: "10px 0 0" }}>
    {shown.map(([label, value]) => <div key={label}>
      <dt style={{ fontSize: ".72rem", color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".04em" }}>{label}</dt>
      <dd style={{ margin: 0, color: "#334155", fontSize: ".9rem", overflowWrap: "anywhere" }}>{value}</dd>
    </div>)}
  </dl>;
}

// Chips in the list view; a full "label — address" list in the single-tool view.
export function ToolLinks({ links, detailed }: { links: ToolLinkItem[]; detailed: boolean }) {
  if (!links.length) {
    return <div style={{ color: "#94a3b8", fontSize: ".85rem" }}>Brak zapisanych linków — użyj „Edytuj dane”.</div>;
  }
  if (!detailed) {
    return <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {links.map(link => <a key={link.url} href={link.url} target="_blank" rel="noreferrer" title={link.url}
        style={{ fontSize: ".85rem" }}>{link.label}</a>)}
    </div>;
  }
  return <ul style={{ margin: 0, paddingLeft: 18, fontSize: ".88rem", color: "#475569" }}>
    {links.map(link => <li key={link.url} style={{ margin: "2px 0" }}>
      <strong style={{ fontWeight: 600 }}>{link.label}:</strong>{" "}
      <a href={link.url} target="_blank" rel="noreferrer" style={{ overflowWrap: "anywhere" }}>{link.url}</a>
    </li>)}
  </ul>;
}

export type DocumentRefLike = { id: number; title: string | null; discovery_source: string | null };

export function DocumentLink({ document }: { document: DocumentRefLike }) {
  return <>
    <Link to={`/read/${document.id}`}>{document.title ?? `#${document.id}`}</Link>
    {document.discovery_source && <span style={{ color: "#94a3b8" }}> ({document.discovery_source})</span>}
  </>;
}

// "dd.mm.yyyy" for the card footer.
export const shortDate = (value: string | null): string | null =>
  value ? new Date(value).toLocaleDateString("pl-PL") : null;
