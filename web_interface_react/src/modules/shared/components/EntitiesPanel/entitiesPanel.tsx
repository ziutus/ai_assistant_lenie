import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";

// NER entities detected in the document (backend: GET/POST /website_entities,
// table document_entities — see docs/ner-integration-plan.md).

interface EntityItem {
  text: string;
  count: number;
}

interface EntitiesByType {
  persName: EntityItem[];
  geogName: EntityItem[];
  placeName: EntityItem[];
}

const chipStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  margin: "2px 4px 2px 0",
  borderRadius: "10px",
  background: "#e8eef7",
  border: "1px solid #b9c8de",
  fontSize: "0.85em",
};

const EntityChips = ({ label, items }: { label: string; items: EntityItem[] }) => {
  if (!items.length) {
    return null;
  }
  return (
    <div style={{ marginTop: "6px" }}>
      <strong>{label}:</strong>{" "}
      {items.map((item) => (
        <span key={item.text} style={chipStyle}>
          {item.text}
          {item.count > 1 && <span style={{ color: "#667" }}> ×{item.count}</span>}
        </span>
      ))}
    </div>
  );
};

const EntitiesPanel = ({ docId }: { docId?: string | number }) => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [entities, setEntities] = React.useState<EntitiesByType | null>(null);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [message, setMessage] = React.useState("");

  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "x-api-key": `${apiKey}`,
  };

  React.useEffect(() => {
    setEntities(null);
    setMessage("");
    if (!docId) {
      return;
    }
    axios
      .get(`${apiUrl}/website_entities`, { params: { id: docId }, headers })
      .then((response) => setEntities(response.data.entities))
      .catch((error) => {
        console.error("Error fetching entities", error);
        setMessage("Nie udało się pobrać encji.");
      });
  }, [docId]);

  const handleRefresh = async () => {
    if (!docId) {
      return;
    }
    setIsRefreshing(true);
    setMessage("");
    try {
      // First call after an ner_service restart loads the spaCy model (~90s) —
      // hence the generous timeout.
      const response = await axios.post(
        `${apiUrl}/website_entities`,
        { id: docId },
        { headers, timeout: 150000 },
      );
      setEntities(response.data.entities);
      if (response.data.refreshed === 0) {
        setMessage("Nie wykryto encji (lub serwis NER jest niedostępny).");
      }
    } catch (error: any) {
      console.error("Error refreshing entities", error);
      setMessage(`Nie udało się wykryć encji: ${error.response?.data?.message || error.message}`);
    }
    setIsRefreshing(false);
  };

  if (!docId) {
    return null;
  }

  const persons = entities?.persName ?? [];
  const places = [...(entities?.geogName ?? []), ...(entities?.placeName ?? [])];
  const isEmpty = !persons.length && !places.length;

  return (
    <div style={{ marginTop: "10px", padding: "8px", border: "1px solid #ddd", borderRadius: "6px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <strong>Osoby i miejsca (NER)</strong>
        <button className={"button"} type="button" disabled={isRefreshing} onClick={handleRefresh}>
          {isRefreshing ? "Wykrywam..." : "Wykryj osoby i miejsca"}
        </button>
      </div>
      <EntityChips label={"Osoby"} items={persons} />
      <EntityChips label={"Miejsca"} items={places} />
      {isEmpty && !message && (
        <div style={{ marginTop: "6px", color: "#667" }}>
          Brak zapisanych encji — użyj przycisku, aby je wykryć.
        </div>
      )}
      {message && <div style={{ marginTop: "6px", color: "#a33" }}>{message}</div>}
    </div>
  );
};

export default EntitiesPanel;
