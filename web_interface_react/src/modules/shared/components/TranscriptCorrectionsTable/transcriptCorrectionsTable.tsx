import React from "react";
import axios from "axios";
import { useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../Pagination/pagination";

// Stored transcript correction rules (GET/POST/PATCH/DELETE /transcript_corrections) for the dictionary page:
// "region" = rules bound to a country tag (kraj-*), one word allowed, replacement inserted verbatim;
// "phrases" = global and per-channel phrase rules (at least two words). Rules rewrite the stored transcript.

export type CorrectionRule = {
  id: number; pattern: string; replacement: string; scope: "global" | "author" | "region";
  author: string | null; country_slug: string | null; active: boolean; note: string | null;
  created_by: string | null; hit_count: number; last_hit_at: string | null;
};

type Mode = "region" | "phrases";

const day = (value: string | null) => (value ? value.replace("T", " ").slice(0, 16) : "—");

const errorText = (failure: unknown, fallback: string) => {
  const err = failure as { response?: { status?: number; data?: { message?: string } } };
  if (err.response?.status === 403) return "Ta operacja wymaga klucza service (zapis nowych reguł działa także z kluczem user).";
  return err.response?.data?.message ?? fallback;
};

const TranscriptCorrectionsTable = ({ mode }: { mode: Mode }) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const requestedSize = Number(searchParams.get("page_size"));
  const pageSize = PAGE_SIZES.includes(requestedSize) ? requestedSize : 50;
  const countryFilter = mode === "region" ? (searchParams.get("country") ?? "") : "";
  const [rules, setRules] = React.useState<CorrectionRule[] | null>(null);
  const [total, setTotal] = React.useState(0);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [confirmDelete, setConfirmDelete] = React.useState<number | null>(null);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [edit, setEdit] = React.useState({ replacement: "", note: "" });
  const [form, setForm] = React.useState({
    scope: mode === "region" ? "region" : "global", pattern: "", replacement: "", country_slug: countryFilter || "kraj-",
    author: "", note: "",
  });

  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "", "Content-Type": "application/json" }), [apiKey]);

  const load = React.useCallback(() => {
    const params: Record<string, string | number> = {
      scope: mode === "region" ? "region" : "global,author", limit: pageSize, offset: (page - 1) * pageSize,
    };
    if (countryFilter) params.country_slug = countryFilter;
    axios.get(`${apiUrl}/transcript_corrections`, { headers, params })
      .then((response) => { setRules(response.data.rules); setTotal(response.data.total ?? response.data.rules.length); setError(""); })
      .catch((failure) => setError(errorText(failure, "Nie udało się pobrać reguł słownika")));
  }, [apiUrl, headers, mode, page, pageSize, countryFilter]);

  React.useEffect(load, [load]);

  const setParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => { if (value) next.set(key, value); else next.delete(key); });
    setSearchParams(next);
  };

  const add = (event: React.FormEvent) => {
    event.preventDefault();
    setNotice(""); setError("");
    const body: Record<string, unknown> = {
      pattern: form.pattern.trim(), replacement: form.replacement, scope: form.scope, note: form.note.trim() || null,
    };
    if (form.scope === "region") body.country_slug = form.country_slug.trim();
    if (form.scope !== "global" && form.author.trim()) body.author = form.author.trim();
    if (form.scope === "author" && !form.author.trim()) { setError("Dla reguły kanału podaj kanał (byline)."); return; }
    axios.post(`${apiUrl}/transcript_corrections`, body, { headers })
      .then(() => {
        setNotice(`Dodano regułę „${form.pattern.trim()}” → „${form.replacement}”. Zadziała przy następnym zastosowaniu słownika.`);
        setForm({ ...form, pattern: "", replacement: "", note: "" });
        load();
      })
      .catch((failure) => setError(errorText(failure, "Nie udało się dodać reguły")));
  };

  const patch = (rule: CorrectionRule, body: Record<string, unknown>, done: string) => {
    setNotice(""); setError("");
    axios.patch(`${apiUrl}/transcript_corrections/${rule.id}`, body, { headers })
      .then(() => { setEditId(null); setNotice(done); load(); })
      .catch((failure) => setError(errorText(failure, "Nie udało się zapisać zmian")));
  };

  const remove = (rule: CorrectionRule) => {
    setNotice(""); setError("");
    axios.delete(`${apiUrl}/transcript_corrections/${rule.id}`, { headers })
      .then(() => { setConfirmDelete(null); setNotice(`Usunięto regułę „${rule.pattern}”.`); load(); })
      .catch((failure) => setError(errorText(failure, "Nie udało się usunąć reguły")));
  };

  const th: React.CSSProperties = { textAlign: "left", padding: "7px 8px", borderBottom: "1px solid #cbd5e1" };
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid #e2e8f0", verticalAlign: "top" };
  const muted: React.CSSProperties = { color: "#64748b", fontSize: "0.85em" };
  const field: React.CSSProperties = { display: "block", marginBottom: 8 };
  const scopeLabel = (rule: CorrectionRule) => rule.scope === "region"
    ? `region ${rule.country_slug}${rule.author ? ` · kanał ${rule.author}` : ""}`
    : rule.scope === "author" ? `kanał ${rule.author}` : "globalna";

  return <div>
    <p style={muted}>
      {mode === "region"
        ? <>Reguły <strong>regionu</strong> poprawiają zapisany transkrypt dokumentów z tagiem kraju (<code>kraj-jemen</code>).
            Wzorzec może być jednym słowem, a zamiennik jest wstawiany dokładnie tak, jak go wpiszesz (np. <code>huti</code> → <code>Huti</code>).
            Reguła działa dopiero po wykryciu kraju dokumentu i zastosowaniu słownika na <code>/ner/:id</code>.</>
        : <>Reguły <strong>fraz</strong> (co najmniej dwa wyrazy) poprawiają transkrypt wszystkich dokumentów albo jednego kanału,
            także przy imporcie napisów. Wielkość pierwszej litery zamiennika dopasowuje się do tekstu.</>}
    </p>
    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {notice && <p role="status" style={{ color: "#15803d" }}>{notice}</p>}

    <form onSubmit={add} style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <h3 style={{ marginTop: 0 }}>Dodaj regułę</h3>
      {mode === "phrases" && (
        <label style={field}>Zakres{" "}
          <select aria-label="Zakres reguły" value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
            <option value="global">globalna (wszystkie kanały)</option>
            <option value="author">tylko jeden kanał</option>
          </select>
        </label>
      )}
      {mode === "region" && (
        <label style={field}>Region (tag kraju){" "}
          <input aria-label="Region" list="correction-countries" value={form.country_slug} required maxLength={100}
            onChange={(e) => setForm({ ...form, country_slug: e.target.value })} />
          <datalist id="correction-countries">
            {[...new Set(["kraj-jemen", ...(rules ?? []).map((rule) => rule.country_slug).filter(Boolean) as string[]])]
              .map((slug) => <option key={slug} value={slug} />)}
          </datalist>
        </label>
      )}
      <label style={field}>Błędny wzorzec{mode === "region" ? " (może być jedno słowo)" : " (co najmniej dwa wyrazy)"}{" "}
        <input aria-label="Wzorzec" value={form.pattern} required maxLength={300}
          onChange={(e) => setForm({ ...form, pattern: e.target.value })} />
      </label>
      <label style={field}>Poprawna wersja{" "}
        <input aria-label="Poprawna wersja" value={form.replacement} required maxLength={300}
          onChange={(e) => setForm({ ...form, replacement: e.target.value })} />
      </label>
      {(mode === "region" || form.scope === "author") && (
        <label style={field}>Kanał (byline){mode === "region" ? ", opcjonalnie — zawęża regułę" : ""}{" "}
          <input aria-label="Kanał" value={form.author} maxLength={200}
            onChange={(e) => setForm({ ...form, author: e.target.value })} />
        </label>
      )}
      <label style={field}>Notatka{" "}
        <input aria-label="Notatka" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      </label>
      <button type="submit">Dodaj</button>
    </form>

    {mode === "region" && (
      <label>Region:{" "}
        <input aria-label="Filtr regionu" placeholder="np. kraj-jemen" value={countryFilter}
          onChange={(e) => setParams({ country: e.target.value.trim() || null, page: null })} />
      </label>
    )}
    {!rules && !error && <p>Ładuję…</p>}
    {rules && <>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 10 }}><thead><tr>
        <th style={th}>Wzorzec → poprawka</th><th style={th}>Zakres</th><th style={th}>Użycie</th><th style={th}>Akcje</th>
      </tr></thead><tbody>
        {rules.map((rule) => <tr key={rule.id} style={rule.active ? undefined : { opacity: 0.55 }}>
          <td style={td}>
            <code>{rule.pattern}</code> → {editId === rule.id
              ? <input aria-label={`Poprawka ${rule.pattern}`} value={edit.replacement}
                  onChange={(e) => setEdit({ ...edit, replacement: e.target.value })} />
              : <strong>{rule.replacement}</strong>}
            <div style={muted}>
              {editId === rule.id
                ? <input aria-label={`Notatka ${rule.pattern}`} value={edit.note}
                    onChange={(e) => setEdit({ ...edit, note: e.target.value })} />
                : <>{rule.note ?? "—"} · #{rule.id}</>}
            </div>
          </td>
          <td style={td}>{scopeLabel(rule)}</td>
          <td style={td}>×{rule.hit_count}<div style={muted}>{day(rule.last_hit_at)}</div></td>
          <td style={td}>
            {editId === rule.id
              ? <><button type="button" onClick={() => patch(rule, { replacement: edit.replacement, note: edit.note.trim() || null }, `Zapisano regułę „${rule.pattern}”.`)}>Zapisz</button>{" "}
                  <button type="button" onClick={() => setEditId(null)}>Anuluj</button></>
              : <>
                  <label><input type="checkbox" aria-label={`Aktywna ${rule.pattern}`} checked={rule.active}
                    onChange={(e) => patch(rule, { active: e.target.checked }, `${e.target.checked ? "Włączono" : "Wyłączono"} regułę „${rule.pattern}”.`)} /> aktywna</label>{" "}
                  <button type="button" onClick={() => { setEditId(rule.id); setEdit({ replacement: rule.replacement, note: rule.note ?? "" }); }}>Edytuj</button>{" "}
                  {confirmDelete === rule.id
                    ? <><button type="button" onClick={() => remove(rule)}>Potwierdź usunięcie</button>{" "}
                        <button type="button" onClick={() => setConfirmDelete(null)}>Anuluj</button></>
                    : <button type="button" onClick={() => setConfirmDelete(rule.id)}>Usuń</button>}
                </>}
          </td>
        </tr>)}
      </tbody></table>
      {!rules.length && <p>Brak reguł{countryFilter ? ` dla regionu ${countryFilter}` : ""}.</p>}
      <Pagination page={page} pageSize={pageSize} total={total} label="reguł słownika"
        onPageChange={(next) => setParams({ page: next > 1 ? String(next) : null })} />
    </>}
  </div>;
};

export default TranscriptCorrectionsTable;
