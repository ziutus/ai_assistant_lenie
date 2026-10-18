import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

// Recipes imported from cookbooks (documents tagged `przepis`, GET /recipes).
// Search folds diacritics on the server ("peczak" finds "pęczak") and covers
// the title and the ingredient list. Filters and paging live in the URL.

export interface RecipeSummary {
  id: number;
  title: string;
  tags: string[];
  servings: string | null;
  meals: string[];
  wege: boolean;
  ingredient_count: number;
  note: string | null;
}

interface MealCount {
  tag: string;
  label: string;
  count: number;
}

const DEFAULT_PAGE_SIZE = 50;

const Recipes = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const [recipes, setRecipes] = React.useState<RecipeSummary[]>([]);
  const [meals, setMeals] = React.useState<MealCount[]>([]);
  const [wegeCount, setWegeCount] = React.useState(0);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  const meal = searchParams.get("meal") ?? "";
  const wege = searchParams.get("wege") === "1";
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
      if (meal) params.meal = meal;
      if (wege) params.wege = "1";
      if (appliedQuery.trim()) params.q = appliedQuery.trim();
      try {
        const response = await axios.get(`${apiUrl}/recipes`, { headers, params });
        if (cancelled) return;
        setRecipes(response.data.recipes ?? []);
        setMeals(response.data.meals ?? []);
        setWegeCount(response.data.wege_count ?? 0);
        setTotal(response.data.total ?? 0);
      } catch (e: any) {
        if (cancelled) return;
        console.error("Error fetching recipes", e);
        setError(`Nie udało się pobrać przepisów: ${e.response?.data?.message || e.message}`);
      }
      setIsLoading(false);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [meal, wege, appliedQuery, page, pageSize, apiUrl, apiKey]);

  const chip = (active: boolean): React.CSSProperties => ({
    padding: "3px 12px",
    borderRadius: 14,
    border: "1px solid #cbd5e1",
    background: active ? "#dbeafe" : "#fff",
    cursor: "pointer",
  });
  const tag = (background: string): React.CSSProperties => ({
    display: "inline-block", padding: "1px 8px", borderRadius: 12, background, fontSize: "0.85em",
  });
  const paging = (
    <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="przepisów"
      onPageChange={(p) => updateParams({ page: p === 1 ? "" : String(p) }, true)} />
  );

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Przepisy</h2>
      <p style={{ color: "#667", marginBottom: 12 }}>
        Przepisy z zaimportowanych książek kucharskich. Szukaj po nazwie dania lub składniku.
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
        <input
          type="text" value={query} placeholder="np. soczewica, pęczak, hummus" style={{ padding: "4px 8px", minWidth: 240 }}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") updateParams({ q: query }); }}
        />
        <button className={"button"} type="button" disabled={isLoading} onClick={() => updateParams({ q: query })}>
          Szukaj
        </button>
        {appliedQuery && (
          <button className={"button"} type="button" onClick={() => { setQuery(""); updateParams({ q: "" }); }}>
            Wyczyść
          </button>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <button type="button" style={chip(!meal)} onClick={() => updateParams({ meal: "" })}>Wszystkie</button>
        {meals.map((m) => (
          <button key={m.tag} type="button" style={chip(meal === m.tag)} onClick={() => updateParams({ meal: meal === m.tag ? "" : m.tag })}>
            {m.label} ({m.count})
          </button>
        ))}
        <button type="button" style={chip(wege)} onClick={() => updateParams({ wege: wege ? "" : "1" })}>
          Z wersją wege ({wegeCount})
        </button>
      </div>

      {isLoading && <div className={"loader"}></div>}
      {error && <p className={"errorText"}>{error}</p>}
      {!isLoading && !error && <p style={{ color: "#667" }}>Znaleziono przepisów: {total}</p>}

      {paging}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {recipes.map((recipe) => (
          <li key={recipe.id} style={{ padding: "10px 8px", borderBottom: "1px solid #eee" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <NavLink to={`/recipes/${recipe.id}`} style={{ fontWeight: 600 }}>{recipe.title}</NavLink>
              {recipe.servings && <span style={tag("#eef2ff")}>porcje: {recipe.servings}</span>}
              {recipe.meals.map((m) => <span key={m} style={tag("#f1f5f9")}>{m}</span>)}
              {recipe.wege && <span style={tag("#dcfce7")}>wege</span>}
            </div>
            <div style={{ color: "#667", marginTop: 4 }}>
              {recipe.ingredient_count} składników{recipe.note ? ` · ${recipe.note}` : ""}
            </div>
          </li>
        ))}
      </ul>

      {paging}

      {!isLoading && !error && !recipes.length && (
        <p style={{ color: "#667" }}>Brak przepisów dla tych filtrów.</p>
      )}
    </div>
  );
};

export default Recipes;
