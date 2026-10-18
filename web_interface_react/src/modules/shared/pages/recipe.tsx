import React from "react";
import axios from "axios";
import { NavLink, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// One recipe (GET /recipes/:id): ingredients, method and where the meal plan
// of the source book serves it. The text is the same Document as in /list and
// /read; the edit form lives at /text/:id.

interface RecipeDetail {
  id: number;
  title: string;
  tags: string[];
  byline: string | null;
  note: string | null;
  servings: string | null;
  meals: string[];
  section: string | null;
  nutrition: string | null;
  notes: string[];
  ingredients: { text: string; label: boolean }[];
  method: string[];
  menu_slots: string[];
}

const sectionTitle: React.CSSProperties = { marginTop: 18, marginBottom: 6 };

const Recipe = () => {
  const { id } = useParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [recipe, setRecipe] = React.useState<RecipeDetail | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };
    const load = async () => {
      setIsLoading(true);
      setError("");
      try {
        const response = await axios.get(`${apiUrl}/recipes/${id}`, { headers });
        if (!cancelled) setRecipe(response.data.recipe);
      } catch (e: any) {
        if (cancelled) return;
        console.error("Error fetching recipe", e);
        setError(`Nie udało się pobrać przepisu: ${e.response?.data?.message || e.message}`);
      }
      setIsLoading(false);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [id, apiUrl, apiKey]);

  return (
    <div style={{ maxWidth: 760 }}>
      <p><NavLink to="/recipes">← Wszystkie przepisy</NavLink></p>
      {isLoading && <div className={"loader"}></div>}
      {error && <p className={"errorText"}>{error}</p>}
      {recipe && (
        <>
          <h2 style={{ marginBottom: 6 }}>{recipe.title}</h2>
          <div style={{ color: "#667", marginBottom: 8 }}>
            {[recipe.servings && `porcje: ${recipe.servings}`, recipe.meals.length && recipe.meals.join(", "), recipe.section]
              .filter(Boolean)
              .join(" · ")}
          </div>
          {recipe.nutrition && <p style={{ fontStyle: "italic" }}>{recipe.nutrition}</p>}
          {recipe.notes.map((note, index) => (
            <blockquote key={index} style={{ margin: "8px 0", paddingLeft: 12, borderLeft: "3px solid #cbd5e1" }}>
              {note}
            </blockquote>
          ))}

          <h3 style={sectionTitle}>Składniki</h3>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {recipe.ingredients.map((item, index) =>
              item.label ? (
                <li key={index} style={{ listStyle: "none", marginLeft: -20, marginTop: 8, fontWeight: 600 }}>{item.text}</li>
              ) : (
                <li key={index}>{item.text}</li>
              ),
            )}
          </ul>

          {recipe.method.length > 0 && (
            <>
              <h3 style={sectionTitle}>Przygotowanie</h3>
              {recipe.method.map((paragraph, index) => (
                <p key={index} style={{ lineHeight: 1.5 }}>{paragraph}</p>
              ))}
            </>
          )}

          {recipe.menu_slots.length > 0 && (
            <>
              <h3 style={sectionTitle}>W jadłospisie</h3>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {recipe.menu_slots.map((slot) => <li key={slot}>{slot}</li>)}
              </ul>
            </>
          )}

          <p style={{ color: "#667", marginTop: 20 }}>
            {[recipe.byline, recipe.note].filter(Boolean).join(" · ")}
            {" · "}
            <NavLink to={`/text/${recipe.id}`}>edytuj dokument</NavLink>
          </p>
        </>
      )}
    </div>
  );
};

export default Recipe;
