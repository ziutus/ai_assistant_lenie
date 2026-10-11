import React from "react";
import axios from "axios";
import { NavLink, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { ageLabel, difficultyLabel, ProjectCardSummary, reviewLabel } from "./projectCards";

// One project card (GET/PATCH /project_cards/:id): the steps to follow with the
// child, plus a small review form (age, difficulty, status, notes) so a card
// can be corrected and marked "sprawdzona" after trying it.

interface ProjectCardDetail extends ProjectCardSummary {
  description: string | null;
  how_it_works: string | null;
  materials: { qty: string; name: string }[];
  tools: string[];
  steps: string[];
  troubleshooting: { problem: string; solution: string }[];
  variants: string[];
  safety: string | null;
  what_child_does: string[];
  what_adult_does: string[];
  safety_checklist: string[];
  review_notes: string | null;
  import_flags: string[];
  illustration_svg: string | null;
}

const sectionTitle: React.CSSProperties = { marginTop: 18, marginBottom: 6 };

const BulletList = ({ items }: { items: string[] }) => (
  <ul style={{ margin: 0, paddingLeft: 20 }}>
    {items.map((item, index) => (
      <li key={index}>{item}</li>
    ))}
  </ul>
);

const ProjectCard = () => {
  const { id } = useParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [card, setCard] = React.useState<ProjectCardDetail | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isSaving, setIsSaving] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [form, setForm] = React.useState({ age_min: "", age_max: "", difficulty: "", review_status: "", review_notes: "" });

  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  const applyCard = (data: ProjectCardDetail) => {
    setCard(data);
    setForm({
      age_min: data.age_min?.toString() ?? "",
      age_max: data.age_max?.toString() ?? "",
      difficulty: data.difficulty?.toString() ?? "",
      review_status: data.review_status,
      review_notes: data.review_notes ?? "",
    });
  };

  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setIsLoading(true);
      setMessage("");
      try {
        const response = await axios.get(`${apiUrl}/project_cards/${id}`, { headers });
        if (!cancelled) applyCard(response.data.card);
      } catch (e: any) {
        if (cancelled) return;
        console.error("Error fetching project card", e);
        setIsError(true);
        setMessage(`Nie udało się pobrać karty: ${e.response?.data?.message || e.message}`);
      }
      setIsLoading(false);
    };
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, apiUrl, apiKey]);

  const toInt = (value: string) => (value.trim() === "" ? null : Number(value));

  const save = async (overrides: Partial<typeof form> = {}) => {
    const values = { ...form, ...overrides };
    setIsSaving(true);
    setMessage("");
    setIsError(false);
    try {
      const response = await axios.patch(
        `${apiUrl}/project_cards/${id}`,
        {
          age_min: toInt(values.age_min),
          age_max: toInt(values.age_max),
          difficulty: toInt(values.difficulty),
          review_status: values.review_status,
          review_notes: values.review_notes,
        },
        { headers },
      );
      applyCard(response.data.card);
      setMessage("Zapisano.");
    } catch (e: any) {
      console.error("Error saving project card", e);
      setIsError(true);
      setMessage(`Nie udało się zapisać: ${e.response?.data?.message || e.message}`);
    }
    setIsSaving(false);
  };

  if (isLoading) return <div className={"loader"}></div>;
  if (!card) return <p className={"errorText"}>{message || "Nie znaleziono karty."}</p>;

  const chip = (background: string): React.CSSProperties => ({
    display: "inline-block", padding: "1px 8px", borderRadius: 12, background, fontSize: "0.85em",
  });
  const fieldStyle: React.CSSProperties = { padding: "4px 8px" };

  return (
    <div style={{ maxWidth: 820 }}>
      <p style={{ marginBottom: 6 }}>
        <NavLink to="/project-cards">← Karty projektów</NavLink>
      </p>
      <h2 style={{ marginBottom: 6 }}>
        <span style={{ color: "#667" }}>№ {String(card.number).padStart(3, "0")}</span> {card.title}
      </h2>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        <span style={chip("#eef2ff")}>{ageLabel(card.age_min, card.age_max)} lat</span>
        <span style={chip("#f1f5f9")}>{difficultyLabel(card.difficulty)}</span>
        {card.time_min !== null && <span style={chip("#f1f5f9")}>{card.time_min} min</span>}
        {card.needs_adult && <span style={chip("#fff7ed")}>z dorosłym</span>}
        <span style={chip(card.review_status === "reviewed" ? "#dcfce7" : "#f3f4f6")}>
          {reviewLabel[card.review_status] ?? card.review_status}
        </span>
        {card.group_name && <span style={chip("#f1f5f9")}>{card.group_name}</span>}
        {card.mechanism && <span style={chip("#f1f5f9")}>{card.mechanism}</span>}
      </div>
      {card.tagline && <p style={{ fontStyle: "italic", margin: "4px 0" }}>{card.tagline}</p>}
      {card.description && <p style={{ color: "#445" }}>{card.description}</p>}
      {card.illustration_svg && (
        // Rendered through <img> so the SVG stays passive (no scripts); the backend also rejects active content.
        <img
          src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(card.illustration_svg)}`}
          alt={`Ilustracja: ${card.title}`}
          style={{ width: "100%", maxWidth: 640, height: "auto", display: "block", margin: "10px 0", borderRadius: 10 }}
        />
      )}
      {card.how_it_works && (
        <>
          <h3 style={sectionTitle}>Jak to działa</h3>
          <p>{card.how_it_works}</p>
        </>
      )}

      {(card.what_child_does.length > 0 || card.what_adult_does.length > 0) && (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          {card.what_child_does.length > 0 && (
            <div style={{ flex: "1 1 300px" }}>
              <h3 style={sectionTitle}>Robi dziecko</h3>
              <BulletList items={card.what_child_does} />
            </div>
          )}
          {card.what_adult_does.length > 0 && (
            <div style={{ flex: "1 1 300px" }}>
              <h3 style={sectionTitle}>Robi dorosły</h3>
              <BulletList items={card.what_adult_does} />
            </div>
          )}
        </div>
      )}

      <h3 style={sectionTitle}>Materiały</h3>
      <ul style={{ margin: 0, paddingLeft: 20 }}>
        {card.materials.map((material, index) => (
          <li key={index}>{[material.qty, material.name].filter(Boolean).join(" × ")}</li>
        ))}
      </ul>
      {card.tools.length > 0 && (
        <>
          <h3 style={sectionTitle}>Narzędzia</h3>
          <BulletList items={card.tools} />
        </>
      )}

      <h3 style={sectionTitle}>Kroki</h3>
      <ol style={{ margin: 0, paddingLeft: 24 }}>
        {card.steps.map((step, index) => (
          <li key={index} style={{ marginBottom: 4 }}>{step}</li>
        ))}
      </ol>

      {card.troubleshooting.length > 0 && (
        <>
          <h3 style={sectionTitle}>Jeśli nie działa</h3>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {card.troubleshooting.map((item, index) => (
              <li key={index}><strong>{item.problem}</strong> {item.solution}</li>
            ))}
          </ul>
        </>
      )}

      {(card.safety || card.safety_checklist.length > 0) && (
        <>
          <h3 style={sectionTitle}>Bezpieczeństwo</h3>
          {card.safety && <p style={{ margin: "0 0 4px" }}>{card.safety}</p>}
          {card.safety_checklist.length > 0 && <BulletList items={card.safety_checklist} />}
        </>
      )}

      {card.variants.length > 0 && (
        <>
          <h3 style={sectionTitle}>Warianty</h3>
          <BulletList items={card.variants} />
        </>
      )}

      <div className="no-print" style={{ marginTop: 26, padding: 12, border: "1px solid #e5e7eb", borderRadius: 8 }}>
        <h3 style={{ marginTop: 0 }}>Przegląd karty</h3>
        {card.import_flags.length > 0 && (
          <p style={{ color: "#92400e" }}>Uwagi z importu: {card.import_flags.join(", ")}</p>
        )}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
          <label>
            Wiek od{" "}
            <input type="number" min={0} max={18} value={form.age_min} style={{ ...fieldStyle, width: 60 }}
              onChange={(e) => setForm({ ...form, age_min: e.target.value })} />
          </label>
          <label>
            do{" "}
            <input type="number" min={0} max={18} value={form.age_max} style={{ ...fieldStyle, width: 60 }}
              onChange={(e) => setForm({ ...form, age_max: e.target.value })} />
          </label>
          <select value={form.difficulty} style={fieldStyle} onChange={(e) => setForm({ ...form, difficulty: e.target.value })}>
            <option value="">Poziom: brak</option>
            <option value="1">Łatwy</option>
            <option value="2">Średni</option>
            <option value="3">Trudny</option>
          </select>
          <select value={form.review_status} style={fieldStyle} onChange={(e) => setForm({ ...form, review_status: e.target.value })}>
            <option value="imported">z PDF-a</option>
            <option value="needs_review">do sprawdzenia</option>
            <option value="reviewed">sprawdzona</option>
          </select>
        </div>
        <textarea
          value={form.review_notes} rows={3} placeholder="Notatki z przeglądu / po zabawie"
          style={{ width: "100%", padding: 6, boxSizing: "border-box" }}
          onChange={(e) => setForm({ ...form, review_notes: e.target.value })}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <button className={"button"} type="button" disabled={isSaving} onClick={() => save()}>Zapisz</button>
          <button
            className={"button"} type="button" disabled={isSaving || card.review_status === "reviewed"}
            onClick={() => save({ review_status: "reviewed" })}
          >
            Oznacz jako sprawdzoną
          </button>
          <button className={"button"} type="button" onClick={() => window.print()}>Drukuj</button>
        </div>
        {message && (
          <p className={isError ? "errorText" : undefined} style={isError ? undefined : { color: "#2e7d43" }}>{message}</p>
        )}
      </div>
    </div>
  );
};

export default ProjectCard;
