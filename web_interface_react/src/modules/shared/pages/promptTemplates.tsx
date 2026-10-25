import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

type Variant = "feed_item" | "document";
type Template = {
  id: number; variant: Variant; version: number; label: string; system_template: string | null; user_template: string;
  note: string | null; is_active: boolean; created_at: string | null;
};
type Builtin = Record<string, { system_template: string | null; user_template: string }>;
type CostSummary = { total: string; per_run: string; runs_with_cost: number; per_accepted: string | null };
type ComparisonRow = {
  model: string; prompt_version: string; prompt_template_id: number | null; runs: number;
  avg_prompt_tokens: number | null; avg_completion_tokens: number | null; avg_latency_ms: number | null;
  cost: Record<string, CostSummary>; suggestions: number; accepted: number; dismissed: number; pending: number;
  accept_rate: number | null; no_match_runs: number; last_run_at: string | null;
};

const VARIANT_LABELS: Record<Variant, string> = { feed_item: "Kuracja feedów", document: "Dokumenty (Tematy)" };
const DAY_OPTIONS = [{ value: 30, label: "30 dni" }, { value: 90, label: "90 dni" }, { value: 365, label: "rok" }, { value: 0, label: "całość" }];
const TIMEOUT_MS = 20_000;
const mono: React.CSSProperties = { fontFamily: "ui-monospace, Menlo, Consolas, monospace", fontSize: ".85rem", width: "100%", boxSizing: "border-box" };

const number = (value: string | number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "—" : Number(value).toLocaleString("pl-PL", { maximumSignificantDigits: digits });

async function request(url: string, init: RequestInit): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const text = await response.text();
    let data: Record<string, unknown> = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
    if (!response.ok) throw new Error(String(data.message || data.error || `HTTP ${response.status}`));
    return data;
  } catch (cause) {
    if (controller.signal.aborted) throw new Error("Brak odpowiedzi z API — zmiana NIE została zapisana.");
    if (cause instanceof TypeError) throw new Error("Nie można połączyć się z API — zmiana NIE została zapisana.");
    throw cause;
  } finally { window.clearTimeout(timer); }
}

export default function PromptTemplates() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const variant: Variant = searchParams.get("variant") === "document" ? "document" : "feed_item";
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "", "Content-Type": "application/json" }), [apiKey]);

  const [templates, setTemplates] = React.useState<Template[]>([]);
  const [builtin, setBuiltin] = React.useState<Builtin>({});
  const [variables, setVariables] = React.useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = React.useState<number | "builtin">("builtin");
  const [system, setSystem] = React.useState("");
  const [user, setUser] = React.useState("");
  const [note, setNote] = React.useState("");
  const [feedItemId, setFeedItemId] = React.useState("");
  const [preview, setPreview] = React.useState<{ system: string | null; user: string; feed_item_id: number | null } | null>(null);
  const [days, setDays] = React.useState(90);
  const [rows, setRows] = React.useState<ComparisonRow[]>([]);
  const [runsConsidered, setRunsConsidered] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");

  const active = templates.find(item => item.is_active);
  const selected = selectedId === "builtin" ? undefined : templates.find(item => item.id === selectedId);
  const baseline = selected ?? builtin[variant];
  const dirty = !!baseline && ((baseline.system_template ?? "") !== system || baseline.user_template !== user);

  const loadEditor = React.useCallback((source: { system_template: string | null; user_template: string } | undefined, nextNote = "") => {
    setSystem(source?.system_template ?? "");
    setUser(source?.user_template ?? "");
    setNote(nextNote);
    setPreview(null);
  }, []);

  const loadTemplates = React.useCallback(async (selectId?: number) => {
    setError("");
    try {
      const data = await request(`${apiUrl}/prompt_templates?variant=${variant}`, { headers });
      const list = (Array.isArray(data.templates) ? data.templates : []) as Template[];
      setTemplates(list);
      setBuiltin((data.builtin || {}) as Builtin);
      setVariables((data.variables || {}) as Record<string, string>);
      const next = list.find(item => item.id === selectId) ?? list.find(item => item.is_active);
      setSelectedId(next ? next.id : "builtin");
      loadEditor(next ?? (data.builtin as Builtin | undefined)?.[variant]);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać szablonów"); }
  }, [apiUrl, headers, variant, loadEditor]);

  const loadComparison = React.useCallback(async () => {
    try {
      const data = await request(`${apiUrl}/prompt_templates/comparison?variant=${variant}&days=${days}`, { headers });
      setRows((Array.isArray(data.rows) ? data.rows : []) as ComparisonRow[]);
      setRunsConsidered(Number(data.runs_considered || 0));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać porównania"); }
  }, [apiUrl, headers, variant, days]);

  React.useEffect(() => { void loadTemplates(); }, [loadTemplates]);
  React.useEffect(() => { void loadComparison(); }, [loadComparison]);

  const pick = (value: string) => {
    setMessage(""); setError("");
    if (value === "builtin") { setSelectedId("builtin"); loadEditor(builtin[variant]); return; }
    const found = templates.find(item => item.id === Number(value));
    if (found) { setSelectedId(found.id); loadEditor(found); }
  };

  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Operacja nie powiodła się"); } finally { setBusy(false); }
  };

  const save = (activate: boolean) => run(async () => {
    const data = await request(`${apiUrl}/prompt_templates`, {
      method: "POST", headers, body: JSON.stringify({ variant, system_template: system || null, user_template: user, note, activate }),
    });
    const created = data.template as Template;
    await loadTemplates(created.id);
    setMessage(activate ? `Zapisano ${created.label} i ustawiono jako aktywną — działa od następnego żądania.` : `Zapisano ${created.label} jako szkic (nieaktywny).`);
  });

  const activateSelected = () => selected && run(async () => {
    await request(`${apiUrl}/prompt_templates/${selected.id}/activate`, { method: "POST", headers });
    await loadTemplates(selected.id);
    setMessage(`${selected.label} jest teraz aktywna.`);
  });

  const showPreview = () => run(async () => {
    const id = feedItemId.trim() ? Number(feedItemId) : undefined;
    if (id !== undefined && !Number.isInteger(id)) throw new Error("Numer wpisu musi być liczbą całkowitą");
    const data = await request(`${apiUrl}/prompt_templates/preview`, {
      method: "POST", headers, body: JSON.stringify({ variant, system_template: system || null, user_template: user, feed_item_id: id }),
    });
    setPreview(data as { system: string | null; user: string; feed_item_id: number | null });
  });

  const money = (row: ComparisonRow) => Object.entries(row.cost).map(([currency, cost]) => (
    <div key={currency} title={`Razem ${number(cost.total)} ${currency} z ${cost.runs_with_cost} przebiegów z ceną`}>
      {number(Number(cost.per_run) * 1000)} {currency}
    </div>
  ));
  const perAccepted = (row: ComparisonRow) => Object.entries(row.cost).map(([currency, cost]) => (
    <div key={currency}>{cost.per_accepted ? `${number(cost.per_accepted)} ${currency}` : "—"}</div>
  ));

  return <div style={{ padding: "0 16px 32px", maxWidth: 1100 }}>
    <h1>Prompty LLM</h1>
    <p style={{ color: "#475569" }}>
      Treść promptu podpowiadającego tematy jest w bazie. Zapis tworzy <strong>nową wersję</strong> (stare zostają, każdy przebieg pamięta wersję i model),
      więc zmiana działa bez wdrażania aplikacji, a poniżej porównasz modele i brzmienia. Wersję można też wybrać ręcznie w <Link to="/feed-review">Kuracji feedów</Link>.
    </p>

    <div role="tablist" style={{ display: "flex", gap: 8, margin: "12px 0" }}>
      {(Object.keys(VARIANT_LABELS) as Variant[]).map(key => (
        <button key={key} type="button" role="tab" aria-selected={key === variant} disabled={key === variant}
          onClick={() => setSearchParams({ variant: key })}>{VARIANT_LABELS[key]}</button>
      ))}
    </div>

    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {message && <p role="status" style={{ color: "#166534" }}>{message}</p>}

    <section aria-label="Edytor">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        <label htmlFor="pt-version">Wersja do edycji:</label>
        <select id="pt-version" value={selectedId} onChange={event => pick(event.target.value)} disabled={busy}>
          <option value="builtin">Wbudowany tekst z kodu{templates.length === 0 ? " (brak wersji w bazie)" : ""}</option>
          {templates.map(item => <option key={item.id} value={item.id}>{item.label}{item.is_active ? " — aktywna" : ""}{item.note ? ` — ${item.note}` : ""}</option>)}
        </select>
        {active && <small style={{ color: "#64748b" }}>W użyciu: <strong>{active.label}</strong></small>}
        {dirty && <strong style={{ color: "#92400e" }}>● niezapisane zmiany</strong>}
      </div>

      <label htmlFor="pt-system"><strong>Prompt systemowy</strong> <small style={{ color: "#64748b" }}>(opcjonalny; wysyłany jako osobna wiadomość)</small></label>
      <textarea id="pt-system" style={mono} rows={3} value={system} onChange={event => setSystem(event.target.value)} />

      <label htmlFor="pt-user" style={{ display: "block", marginTop: 8 }}><strong>Prompt użytkownika</strong></label>
      <textarea id="pt-user" style={mono} rows={20} value={user} onChange={event => setUser(event.target.value)} />

      <details style={{ margin: "8px 0", color: "#475569" }}>
        <summary>Składnia szablonu i zmienne</summary>
        <p>Szablon Jinja2 (tryb bezpieczny): <code>{"{{ zmienna }}"}</code>, <code>{"{% if schema %}…{% endif %}"}</code>. Nieznana zmienna blokuje zapis.</p>
        <ul>{Object.entries(variables).map(([name, description]) => <li key={name}><code>{`{{ ${name} }}`}</code> — {description}</li>)}</ul>
        <p>Dla modeli bez trybu strukturalnego schemat JSON trafia do <code>schema</code>; dla pozostałych <code>schema</code> jest pusty, a schemat idzie osobno jako <code>response_format</code>.
          Kod nadal wymaga od modelu kluczy <code>suggestions</code>, <code>no_match</code>{variant === "feed_item" ? " i new_topics" : ""} — nie usuwaj ich z instrukcji.</p>
      </details>

      <label htmlFor="pt-note">Notatka do wersji <small style={{ color: "#64748b" }}>(po co ta zmiana, np. „krótszy, bez przykładów”)</small></label>
      <input id="pt-note" style={{ ...mono, fontFamily: "inherit" }} maxLength={300} value={note} onChange={event => setNote(event.target.value)} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 10 }}>
        <button type="button" disabled={busy || !user.trim()} onClick={() => void save(true)}>Zapisz jako nową wersję i aktywuj</button>
        <button type="button" disabled={busy || !user.trim()} onClick={() => void save(false)}>Zapisz jako szkic (bez aktywacji)</button>
        {selected && !selected.is_active && <button type="button" disabled={busy || dirty} onClick={() => void activateSelected()}>Aktywuj {selected.label}</button>}
        <button type="button" disabled={busy || !builtin[variant]} onClick={() => { setSelectedId("builtin"); loadEditor(builtin[variant]); }}>Wczytaj tekst wbudowany</button>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 10 }}>
        <button type="button" disabled={busy || !user.trim()} onClick={() => void showPreview()}>Podgląd (bez wywołania modelu)</button>
        {variant === "feed_item" && <>
          <label htmlFor="pt-feed-item">na wpisie nr</label>
          <input id="pt-feed-item" inputMode="numeric" size={8} placeholder="np. 12382" value={feedItemId} onChange={event => setFeedItemId(event.target.value)} />
        </>}
      </div>
      {preview && <div aria-label="Podgląd">
        {preview.system && <><h3>System</h3><pre style={{ ...mono, whiteSpace: "pre-wrap", background: "#f1f5f9", padding: 8 }}>{preview.system}</pre></>}
        <h3>Użytkownik{preview.feed_item_id ? ` (wpis ${preview.feed_item_id})` : " (przykładowy materiał)"}</h3>
        <pre style={{ ...mono, whiteSpace: "pre-wrap", background: "#f1f5f9", padding: 8 }}>{preview.user}</pre>
      </div>}
    </section>

    <section aria-label="Porównanie" style={{ marginTop: 32 }}>
      <h2>Porównanie modeli i wersji promptu</h2>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label htmlFor="pt-days">Okres:</label>
        <select id="pt-days" value={days} onChange={event => setDays(Number(event.target.value))}>
          {DAY_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <small style={{ color: "#64748b" }}>Zakończone przebiegi: {runsConsidered}. „Zaakceptowane” liczy decyzje człowieka, więc porównuj próby o podobnej liczbie wpisów.</small>
      </div>
      {rows.length === 0 ? <p>Brak zakończonych przebiegów w tym okresie.</p> : <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", marginTop: 8 }}>
          <thead><tr style={{ textAlign: "left", borderBottom: "2px solid #cbd5e1" }}>
            <th>Prompt</th><th>Model</th><th>Przebiegi</th><th>Tokeny (wej./wyj.)</th><th>Czas</th>
            <th title="Średni koszt przeliczony na 1000 przebiegów (tylko przebiegi z ceną)">Koszt / 1000</th>
            <th>Zaakc. / odrzuc.</th><th>% zaakc.</th><th title="Koszt podzielony przez liczbę zaakceptowanych podpowiedzi">Koszt / zaakc.</th><th>Brak dopasowania</th>
          </tr></thead>
          <tbody>{rows.map(row => <tr key={`${row.model}|${row.prompt_version}`} style={{ borderBottom: "1px solid #e2e8f0", verticalAlign: "top" }}>
            <td>{row.prompt_version}</td>
            <td>{row.model.replace(/^openrouter\//, "")}</td>
            <td>{row.runs}</td>
            <td>{number(row.avg_prompt_tokens, 4)} / {number(row.avg_completion_tokens, 4)}</td>
            <td>{row.avg_latency_ms === null ? "—" : `${number(row.avg_latency_ms / 1000, 2)} s`}</td>
            <td>{Object.keys(row.cost).length ? money(row) : "brak ceny"}</td>
            <td>{row.accepted} / {row.dismissed}{row.pending ? <small style={{ color: "#64748b" }}> (+{row.pending} czeka)</small> : null}</td>
            <td>{row.accept_rate === null ? "—" : `${Math.round(row.accept_rate * 100)}%`}</td>
            <td>{Object.keys(row.cost).length ? perAccepted(row) : "—"}</td>
            <td>{row.no_match_runs} / {row.runs}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </section>
  </div>;
}
