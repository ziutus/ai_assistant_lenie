import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// Usage statistics of the NER correction dictionary: GET /ner_corrections/stats.
// Shows which manual rules actually fire and how often, so recurring mistakes
// can be promoted from "another manual rule" to a code fix.

type Rule = {
  id: number; match_lemma: string; match_entity_type: string; corrected_text: string;
  corrected_entity_type: string | null; scope: string; reason: string; approved_by: string;
  source_document_id: number | null; created_at: string | null;
  applications: number; documents: number; last_applied_at: string | null;
};
type TypeRow = { type_before: string; type_after: string; applications: number; documents: number };
type Stats = {
  totals: { rules: number; unused_rules: number; applications: number; exclusions: number };
  rules: Rule[]; by_type: TypeRow[]; exclusions_by_type: { entity_type: string; rules: number }[];
};

const day = (value: string | null) => (value ? value.replace("T", " ").slice(0, 16) : "—");

const NerCorrections = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [error, setError] = React.useState("");
  const [onlyUnused, setOnlyUnused] = React.useState(false);

  React.useEffect(() => {
    axios.get(`${apiUrl}/ner_corrections/stats`, { headers: { "x-api-key": apiKey ?? "" } })
      .then(response => setStats(response.data))
      .catch(e => setError(e.response?.data?.message ?? "Nie udało się pobrać statystyk poprawek NER"));
  }, [apiUrl, apiKey]);

  const tableStyle: React.CSSProperties = { width: "100%", borderCollapse: "collapse", marginTop: 10 };
  const th: React.CSSProperties = { textAlign: "left", padding: "7px 8px", borderBottom: "1px solid #cbd5e1" };
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid #e2e8f0", verticalAlign: "top" };
  const tile: React.CSSProperties = { padding: 12, minWidth: 150, border: "1px solid #cbd5e1", borderRadius: 8 };

  return <div>
    <h2>Poprawki NER — statystyki</h2>
    <p style={{ color: "#64748b" }}>
      Reguły ze słownika korekt (<code>ner_corrections</code>) i to, ile razy faktycznie zadziałały.
      Reguła, która działa często w wielu dokumentach, to sygnał, że błąd warto naprawić w kodzie.
    </p>
    {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
    {!stats && !error && <p>Ładuję…</p>}
    {stats && <>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div style={tile}><strong style={{ fontSize: "1.3em" }}>{stats.totals.rules}</strong><br/>reguł korekt</div>
        <div style={tile}><strong style={{ fontSize: "1.3em" }}>{stats.totals.applications}</strong><br/>zadziałań łącznie</div>
        <div style={tile}><strong style={{ fontSize: "1.3em" }}>{stats.totals.unused_rules}</strong><br/>reguł bez zadziałań</div>
        <div style={tile}><strong style={{ fontSize: "1.3em" }}>{stats.totals.exclusions}</strong><br/>reguł wykluczeń</div>
      </div>

      <h3>Reguły</h3>
      <label><input type="checkbox" checked={onlyUnused} onChange={e => setOnlyUnused(e.target.checked)} /> tylko nieużyte</label>
      <table style={tableStyle}><thead><tr>
        <th style={th}>Reguła</th><th style={th}>Zadziałań</th><th style={th}>Dokumentów</th>
        <th style={th}>Ostatnio</th><th style={th}>Uzasadnienie</th>
      </tr></thead><tbody>
        {stats.rules.filter(r => !onlyUnused || r.applications === 0).map(r => <tr key={r.id}>
          <td style={td}>
            <strong>{r.match_lemma}</strong> → <strong>{r.corrected_text}</strong>
            <div style={{ color: "#64748b", fontSize: "0.85em" }}>
              #{r.id} · {r.match_entity_type}{r.corrected_entity_type ? ` → ${r.corrected_entity_type}` : ""} · {r.scope}
              {r.source_document_id != null && <> · <NavLink to={`/read/${r.source_document_id}`}>dok. #{r.source_document_id}</NavLink></>}
            </div>
          </td>
          <td style={td}>{r.applications}</td><td style={td}>{r.documents}</td>
          <td style={td}>{day(r.last_applied_at)}</td>
          <td style={td}>{r.reason}<div style={{ color: "#64748b", fontSize: "0.85em" }}>{r.approved_by} · {day(r.created_at)}</div></td>
        </tr>)}
      </tbody></table>
      {!stats.rules.length && <p>Brak reguł korekt.</p>}

      <h3>Zmiany typu encji</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Przed</th><th style={th}>Po</th><th style={th}>Zadziałań</th><th style={th}>Dokumentów</th></tr></thead><tbody>
        {stats.by_type.map((r, i) => <tr key={i}><td style={td}>{r.type_before}</td><td style={td}>{r.type_after}</td><td style={td}>{r.applications}</td><td style={td}>{r.documents}</td></tr>)}
      </tbody></table>
      {!stats.by_type.length && <p>Żadna reguła jeszcze nie zadziałała.</p>}

      <h3>Wykluczenia wg typu</h3>
      <table style={tableStyle}><thead><tr><th style={th}>Typ encji</th><th style={th}>Reguł</th></tr></thead><tbody>
        {stats.exclusions_by_type.map(r => <tr key={r.entity_type}><td style={td}>{r.entity_type}</td><td style={td}>{r.rules}</td></tr>)}
      </tbody></table>
    </>}
  </div>;
};

export default NerCorrections;
