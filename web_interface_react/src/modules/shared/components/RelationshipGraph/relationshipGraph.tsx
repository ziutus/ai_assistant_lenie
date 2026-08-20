import React from "react";
import {
  DataSet,
  Network,
  type Edge as VisEdge,
  type Node as VisNode,
  type Options,
} from "vis-network/standalone";

export interface RelationshipGraphNode {
  id: string;
  type: "document" | "publisher" | "information_source" | "cited_publication" | "organization";
  label: string;
  href?: string;
  external_url?: string | null;
  linked_to_source?: boolean;
  context_only?: boolean;
  // Organization.description (set via PATCH /organizations/<id> or the
  // organization_descriptions_backfill.py LLM backfill) — shown as a native
  // hover tooltip on the node and in the details panel below the graph.
  description?: string | null;
}

export interface RelationshipGraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
}

export interface RelationshipGraphData {
  nodes: RelationshipGraphNode[];
  edges: RelationshipGraphEdge[];
}

const TYPE_LABELS: Record<RelationshipGraphNode["type"], string> = {
  document: "dokument",
  publisher: "publikacja",
  information_source: "źródło informacji",
  cited_publication: "cytowana publikacja",
  organization: "organizacja",
};

const EDGE_LABELS: Record<string, string> = {
  publisher: "opublikowano w",
  original_reporting: "źródło ustaleń",
  republication: "przedruk / opracowanie",
  cited: "cytowanie",
  data_source: "źródło danych",
  cited_publication: "cytuje",
  issued_statement: "komunikat podany przez",
  reported_by: "relacjonowany przez",
  cited_by: "przywołany przez",
  data_provided_to: "dane przekazane",
};

const NODE_COLORS: Record<RelationshipGraphNode["type"], string> = {
  document: "#0369a1",
  publisher: "#0f766e",
  information_source: "#7c3aed",
  cited_publication: "#b45309",
  organization: "#475569",
};

const GRAPH_OPTIONS: Options = {
  autoResize: true,
  layout: { improvedLayout: true },
  nodes: {
    shape: "dot",
    size: 22,
    borderWidth: 2,
    font: { face: "system-ui", size: 14, color: "#334155" },
  },
  edges: {
    smooth: false,
    width: 1.4,
    color: { color: "#64748b", highlight: "#0f766e" },
    arrows: { to: { enabled: true, scaleFactor: 0.72 } },
  },
  physics: {
    enabled: true,
    solver: "forceAtlas2Based",
    forceAtlas2Based: {
      gravitationalConstant: -32,
      centralGravity: 0.018,
      springLength: 88,
      springConstant: 0.07,
      avoidOverlap: 1,
    },
    stabilization: { enabled: true, iterations: 140, fit: true },
  },
  interaction: {
    dragNodes: true,
    dragView: true,
    zoomView: true,
    navigationButtons: false,
    keyboard: false,
  },
};

export default function RelationshipGraph({ data }: { data: RelationshipGraphData }) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const selected = data.nodes.find(node => node.id === selectedId) ?? null;
  const selectedEdges = selected ? data.edges.filter(edge => edge.source === selected.id || edge.target === selected.id) : [];

  React.useEffect(() => {
    const container = containerRef.current;
    if (!container || data.nodes.length < 2) return undefined;
    const nodes = new DataSet<VisNode>(data.nodes.map(node => {
      const color = node.context_only ? "#94a3b8" : NODE_COLORS[node.type];
      return {
        id: node.id,
        label: node.label,
        title: node.description ?? undefined,
        color: { background: color, border: color, highlight: { background: color, border: "#0f172a" } },
      };
    }));
    const edges = new DataSet<VisEdge>(data.edges.map(edge => ({
      id: edge.id,
      from: edge.source,
      to: edge.target,
    })));
    const network = new Network(container, { nodes, edges }, GRAPH_OPTIONS);
    network.on("click", params => setSelectedId(params.nodes.length ? String(params.nodes[0]) : null));
    return () => network.destroy();
  }, [data]);

  if (data.nodes.length < 2) return null;

  return (
    <details open style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 10, marginTop: 12 }}>
      <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
        🕸️ Graf powiązań ({data.nodes.length})
      </summary>
      <div ref={containerRef} aria-label="Graf powiązań dokumentu" style={{ height: 365, marginTop: 8 }} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 10px", fontSize: "0.72em", color: "#475569" }}>
        {(Object.keys(TYPE_LABELS) as RelationshipGraphNode["type"][]).filter(type => data.nodes.some(node => node.type === type)).map(type => (
          <span key={type}><span aria-hidden="true" style={{ color: NODE_COLORS[type] }}>●</span> {TYPE_LABELS[type]}</span>
        ))}
      </div>
      {selected && <div style={{ marginTop: 8, fontSize: "0.8em", color: "#334155" }}>
        <strong>{selected.label}</strong> <span style={{ color: "#64748b" }}>({TYPE_LABELS[selected.type]})</span>
        {selected.external_url ? <> {" "}<a href={selected.external_url} target="_blank" rel="noreferrer">otwórz ↗</a></>
          : selected.href ? <> {" "}<a href={selected.href}>zobacz</a></> : null}
        {selected.description && <div style={{ color: "#475569", marginTop: 2 }}>{selected.description}</div>}
        {selectedEdges.length > 0 && <div style={{ color: "#64748b", marginTop: 2 }}>
          {selectedEdges.map(edge => EDGE_LABELS[edge.type] ?? edge.type).filter((value, index, values) => values.indexOf(value) === index).join(" · ")}
        </div>}
      </div>}
    </details>
  );
}
