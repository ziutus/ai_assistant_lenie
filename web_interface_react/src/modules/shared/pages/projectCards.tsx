import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

// Project cards library (table `project_cards`, GET /project_cards). The age
// filter shows cards whose printed range contains the child's age; "stretch"
// also shows cards starting a year above it, marked "do spróbowania z
// dorosłym". Filters and paging live in the URL so a view can be shared.

export interface ProjectCardSummary {
  id: number;
  series: string;
  number: number;
  title: string;
  topic: string | null;
  group_name: string | null;
  tagline: string | null;
  mechanism: string | null;
  age_min: number | null;
  age_max: number | null;
  time_min: number | null;
  time_max: number | null;
  difficulty: number | null;
  needs_adult: boolean;
  review_status: "imported" | "needs_review" | "reviewed";
  age_fit?: "ok" | "stretch" | null;
}

interface GroupCount {
  name: string;
  count: number;
}

export const difficultyLabel = (difficulty: number | null) =>
  difficulty === 1 ? "Łatwy" : difficulty === 2 ? "Średni" : difficulty === 3 ? "Trudny" : "—";

export const reviewLabel: Record<string, string> = {
  imported: "z PDF-a",
  needs_review: "do sprawdzenia",
  reviewed: "sprawdzona",
};

export const ageLabel = (min: number | null, max: number | null) =>
  min === null ? "—" : max === null || max === min ? `${min}+` : `${min}–${max}`;

const AGE_STORAGE_KEY = "projectCardsAge";
const DEFAULT_PAGE_SIZE = 50;

const readStoredAge = (): string => {
  try {
    return window.localStorage.getItem(AGE_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
};

const ProjectCards = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const [cards, setCards] = React.useState<ProjectCardSummary[]>([]);
  const [groups, setGroups] = React.useState<GroupCount[]>([]);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  // The age falls back to the last value the user typed (localStorage).
  const age = searchParams.get("age") ?? readStoredAge();
  const stretch = searchParams.get("stretch") === "1";
  const maxDifficulty = searchParams.get("max_difficulty") ?? "";
  const group = searchParams.get("group") ?? "";
  const reviewStatus = searchParams.get("review_status") ?? "";
  const appliedQuery = searchParams.get("q") ?? "";
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const requestedSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const pageSize = PAGE_SIZES.includes(requestedSize) ? requestedSize : DEFAULT_PAGE_SIZE;
  const [query, setQuery] = React.useState(appliedQuery);

  const updateParams = (changes: Record<string, string>, keepPage = false) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
    if (!keepPage) next.delete("page");
    setSearchParams(next, { replace: true });
  };

  React.useEffect(() => {
    let cancelled = false;
    const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };
    const load = async () => {
      setIsLoading(true);
      setError("");
      const params: Record<string, string> = { limit: String(pageSize), offset: String((page - 1) * pageSize) };
      if (age) {
        params.age = age;
        if (stretch) params.stretch = "1";
      }
      if (maxDifficulty) params.max_difficulty = maxDifficulty;
      if (group) params.group = group;
      if (reviewStatus) params.review_status = reviewStatus;
      if (appliedQuery.trim()) params.q = appliedQuery.trim();
      try {
        const response = await axios.get(`${apiUrl}/project_cards`, { headers, params });
        if (cancelled) return;
        setCards(response.data.cards ?? []);
        setGroups(response.data.groups ?? []);
        setTotal(response.data.total ?? 0);
      } catch (e: any) {
        if (cancelled) return;
        console.error("Error fetching project cards", e);
        setError(`Nie udało się pobrać kart: ${e.response?.data?.message || e.message}`);
      }
      setIsLoading(false);
    };
    load();
    try {
      window.localStorage.setItem(AGE_STORAGE_KEY, age);
    } catch {
      // storage unavailable: the age filter just isn't remembered
    }
    return () => {
      cancelled = true;
    };
  }, [age, stretch, maxDifficulty, group, reviewStatus, appliedQuery, page, pageSize, apiUrl, apiKey]);

  const fieldStyle: React.CSSProperties = { padding: "4px 8px" };
  const chip = (background: string): React.CSSProperties => ({
    display: "inline-block", padding: "1px 8px", borderRadius: 12, background, fontSize: "0.85em",
  });
  const paging = (
    <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="kart"
      onPageChange={(p) => updateParams({ page: p === 1 ? "" : String(p) }, true)} />
  );

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Karty projektów</h2>
      <p style={{ color: "#667", marginBottom: 12 }}>
        Projekty do zrobienia z dzieckiem. Podaj wiek, żeby zobaczyć tylko pasujące karty.
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
        <label>
          Wiek dziecka{" "}
          <input
            type="number" min={0} max={18} value={age} placeholder="np. 5" style={{ ...fieldStyle, width: 70 }}
            onChange={(e) => updateParams({ age: e.target.value })}
          />
        </label>
        <label title="Pokaż też karty, które zaczynają się rok wyżej (z pomocą dorosłego)">
          <input
            type="checkbox" checked={stretch} disabled={!age}
            onChange={(e) => updateParams({ stretch: e.target.checked ? "1" : "" })}
          />{" "}
          pokaż o rok trudniejsze
        </label>
        <select value={maxDifficulty} onChange={(e) => updateParams({ max_difficulty: e.target.value })} style={fieldStyle}>
          <option value="">Każdy poziom</option>
          <option value="1">Tylko łatwe</option>
          <option value="2">Do średnich</option>
        </select>
        <select value={group} onChange={(e) => updateParams({ group: e.target.value })} style={fieldStyle}>
          <option value="">Wszystkie grupy</option>
          {groups.map((g) => (
            <option key={g.name} value={g.name}>{g.name} ({g.count})</option>
          ))}
        </select>
        <select value={reviewStatus} onChange={(e) => updateParams({ review_status: e.target.value })} style={fieldStyle}>
          <option value="">Każdy status</option>
          <option value="reviewed">Sprawdzone</option>
          <option value="needs_review">Do sprawdzenia</option>
          <option value="imported">Z PDF-a</option>
        </select>
        <input
          type="text" value={query} placeholder="Szukaj w tytule/opisie" style={{ ...fieldStyle, minWidth: 180 }}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") updateParams({ q: query }); }}
        />
        <button className={"button"} type="button" disabled={isLoading} onClick={() => updateParams({ q: query })}>
          Szukaj
        </button>
      </div>

      {isLoading && <div className={"loader"}></div>}
      {error && <p className={"errorText"}>{error}</p>}
      {!isLoading && !error && <p style={{ color: "#667" }}>Znaleziono kart: {total}</p>}

      {paging}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {cards.map((card) => (
          <li key={card.id} style={{ padding: "10px 8px", borderBottom: "1px solid #eee" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ color: "#667" }}>№ {String(card.number).padStart(3, "0")}</span>
              <NavLink to={`/project-cards/${card.id}`} style={{ fontWeight: 600 }}>{card.title}</NavLink>
              <span style={chip("#eef2ff")}>{ageLabel(card.age_min, card.age_max)} lat</span>
              <span style={chip("#f1f5f9")}>{difficultyLabel(card.difficulty)}</span>
              {card.time_min !== null && <span style={chip("#f1f5f9")}>{card.time_min} min</span>}
              {card.needs_adult && <span style={chip("#fff7ed")}>z dorosłym</span>}
              {card.age_fit === "stretch" && <span style={chip("#fef3c7")}>do spróbowania z dorosłym</span>}
              <span style={chip(card.review_status === "reviewed" ? "#dcfce7" : "#f3f4f6")}>
                {reviewLabel[card.review_status] ?? card.review_status}
              </span>
            </div>
            <div style={{ color: "#667", marginTop: 4 }}>
              {[card.group_name, card.mechanism].filter(Boolean).join(" · ")}
              {card.tagline ? ` — ${card.tagline}` : ""}
            </div>
          </li>
        ))}
      </ul>

      {paging}

      {!isLoading && !error && !cards.length && (
        <p style={{ color: "#667" }}>Brak kart dla tych filtrów.</p>
      )}
    </div>
  );
};

export default ProjectCards;
