import React from "react";

export interface MergeSourceSummary {
  id: number;
  canonical_name: string;
  source_type: string | null;
  domain: string | null;
  description: string | null;
  document_count: number;
}

export interface MergeOrganizationSummary {
  id: number;
  canonical_name: string;
  organization_type: string | null;
  description: string | null;
  aliases: string[];
  document_count: number;
  information_source: MergeSourceSummary | null;
}

export interface MergePreviewData {
  source: MergeOrganizationSummary;
  target: MergeOrganizationSummary;
  effects: {
    alias_added: string | null;
    aliases_moved: string[];
    documents_moved: number;
    documents_in_both: number;
    entities_renamed: number;
    source_action: "merge_sources" | "move_source" | "none";
    source_fields_dropped: string[];
  };
}

const FIELD_LABELS: Record<string, string> = { source_type: "typ", domain: "strona", description: "opis" };
const dash = <span style={{ color: "#999" }}>—</span>;

const sourceLine = (source: MergeSourceSummary | null) => {
  if (!source) return dash;
  const parts = [source.canonical_name, source.source_type, source.domain].filter(Boolean).join(" · ");
  return <>{parts} <span style={{ color: "#667" }}>({source.document_count} dok.)</span></>;
};

const cellStyle: React.CSSProperties = { padding: "3px 8px", verticalAlign: "top", borderTop: "1px solid #dde" };

/** Side-by-side comparison of two organizations and what merging the first into the second does. */
const OrganizationMergePreview = ({
  preview,
  busy,
  onConfirm,
  onCancel,
}: {
  preview: MergePreviewData;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) => {
  const { source, target, effects } = preview;
  const rows: [string, React.ReactNode, React.ReactNode][] = [
    ["Nazwa", <strong key="s">{source.canonical_name}</strong>, <strong key="t">{target.canonical_name}</strong>],
    ["Typ", source.organization_type ?? dash, target.organization_type ?? dash],
    ["Opis", source.description ?? dash, target.description ?? dash],
    ["Aliasy", source.aliases.length ? source.aliases.join(", ") : dash, target.aliases.length ? target.aliases.join(", ") : dash],
    ["Dokumenty", source.document_count, target.document_count],
    ["Źródło informacji", sourceLine(source.information_source), sourceLine(target.information_source)],
    ["Opis źródła", source.information_source?.description ?? dash, target.information_source?.description ?? dash],
  ];
  const changes: string[] = [];
  if (effects.alias_added) changes.push(`„${effects.alias_added}” zostanie aliasem „${target.canonical_name}” (przyszłe wykrycia trafią do niej automatycznie).`);
  if (effects.aliases_moved.length) changes.push(`Aliasy przeniesione do „${target.canonical_name}”: ${effects.aliases_moved.join(", ")}.`);
  if (effects.documents_moved) changes.push(`${effects.documents_moved} dok. zostanie powiązanych z „${target.canonical_name}”.`);
  if (effects.documents_in_both) changes.push(`${effects.documents_in_both} dok. ma obie organizacje — zostanie jedno powiązanie.`);
  if (effects.entities_renamed) changes.push(`${effects.entities_renamed} encji w dokumentach zmieni nazwę na „${target.canonical_name}”.`);
  if (effects.source_action === "merge_sources") {
    changes.push(`Źródła zostaną scalone („${source.information_source?.canonical_name}” → „${target.information_source?.canonical_name}”): powiązania z dokumentami i aliasy przejdzie do drugiego.`);
    if (effects.source_fields_dropped.length) {
      changes.push(`Utracone dane źródła (cel ma własne): ${effects.source_fields_dropped.map((f) => FIELD_LABELS[f] ?? f).join(", ")}.`);
    }
  } else if (effects.source_action === "move_source") {
    changes.push(`Źródło „${source.information_source?.canonical_name}” stanie się źródłem „${target.canonical_name}” (z jego nazwą).`);
  }
  changes.push(`Organizacja „${source.canonical_name}” zniknie z rejestru. Zmiana jest globalna i nieodwracalna z poziomu panelu.`);

  return (
    <div style={{ marginTop: 8, padding: 8, background: "#f0f6ff", borderRadius: 6 }}>
      <div style={{ marginBottom: 4 }}>
        Połączyć „<strong>{source.canonical_name}</strong>” z „<strong>{target.canonical_name}</strong>”?
      </div>
      <table style={{ borderCollapse: "collapse", fontSize: "0.9em" }}>
        <thead>
          <tr style={{ textAlign: "left", color: "#667" }}>
            <th style={cellStyle} />
            <th style={cellStyle}>Łączona (zniknie)</th>
            <th style={cellStyle}>Zostaje (cel)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, left, right]) => (
            <tr key={label}>
              <th style={{ ...cellStyle, textAlign: "left", fontWeight: 600 }}>{label}</th>
              <td style={cellStyle}>{left}</td>
              <td style={cellStyle}>{right}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 6, fontWeight: 600 }}>Co się stanie:</div>
      <ul style={{ margin: "2px 0 6px 18px", padding: 0 }}>
        {changes.map((line) => <li key={line}>{line}</li>)}
      </ul>
      <button className={"button"} type="button" disabled={busy} onClick={onConfirm}>Połącz</button>
      <button type="button" disabled={busy} style={{ marginLeft: 8 }} onClick={onCancel}>Anuluj</button>
    </div>
  );
};

export default OrganizationMergePreview;
