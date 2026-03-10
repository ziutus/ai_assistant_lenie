import axios from "axios";
import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

const STORAGE_KEY = "lenie_document_states";

interface DocumentStatesData {
  states: string[];
  types: string[];
  errors: string[];
}

function loadCached(): DocumentStatesData | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export const useDocumentStates = () => {
  const cached = React.useMemo(loadCached, []);
  const [states, setStates] = React.useState<string[]>(cached?.states ?? []);
  const [types, setTypes] = React.useState<string[]>(cached?.types ?? []);
  const [errors, setErrors] = React.useState<string[]>(cached?.errors ?? []);
  const [loading, setLoading] = React.useState(!cached);
  const [error, setError] = React.useState<string | null>(null);
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  React.useEffect(() => {
    if (!apiUrl || !apiKey) return;

    const controller = new AbortController();

    const fetchStates = async () => {
      setLoading(true);
      try {
        const response = await axios.get(`${apiUrl}/document_states`, {
          headers: { "x-api-key": `${apiKey}` },
          signal: controller.signal,
        });
        const data: DocumentStatesData = response.data;
        setStates(data.states);
        setTypes(data.types);
        setErrors(data.errors);
        setError(null);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      } catch (err: unknown) {
        if (axios.isCancel(err)) return;
        const message = err instanceof Error ? err.message : "Unknown error";
        console.error("Failed to fetch document states:", err);
        setError(message);
        // Fallback to cached values
        const fallback = loadCached();
        if (fallback) {
          setStates(fallback.states);
          setTypes(fallback.types);
          setErrors(fallback.errors);
        }
      } finally {
        setLoading(false);
      }
    };

    fetchStates();

    return () => controller.abort();
  }, [apiUrl, apiKey]);

  return { states, types, errors, loading, error };
};
