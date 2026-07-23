import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";
import { buildExplicitSearchPayload } from "../utils/searchCriteria";

export interface SearchInterpretation {
  query: string | null;
  author_name: string | null;
  publisher_name: string | null;
  publisher_domain: string | null;
  discovery_source_name: string | null;
  collection_name: string | null;
  published_on_from: string | null;
  published_on_to: string | null;
  ingested_at_from: string | null;
  ingested_at_to: string | null;
  subject_period_start_year: number | null;
  subject_period_end_year: number | null;
  temporal_expression: string | null;
  document_types: string[];
  languages: string[];
  without_embedding?: boolean;
  sort: string;
  interpretation_summary: string;
  warnings: string[];
  clarification_required: boolean;
  clarification_question: string | null;
  model_confidence: string;
}

export interface SearchResponse {
  search_id: number | null;
  interpretation: SearchInterpretation;
  status: string;
  fallback_used: boolean;
  results: any[];
  clarification_required: boolean;
  clarification_question: string | null;
  pagination?: {
    limit: number;
    offset: number;
    returned: number;
    has_more: boolean;
  };
}

export const buildNaturalSearchPayload = (naturalQuery: string, limit: string, offset = 0) => ({
  natural_query: naturalQuery.trim(),
  limit: Number(limit),
  ...(offset ? { offset } : {}),
});

export const useSearch = () => {
  const [message, setMessage] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [results, setResults] = React.useState<any[] | null>(null);
  const [searchResponse, setSearchResponse] = React.useState<SearchResponse | null>(null);
  const [originSearchId, setOriginSearchId] = React.useState<number | null>(null);
  const [feedbackMessage, setFeedbackMessage] = React.useState("");
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const handleSearch = React.useCallback(async (naturalQuery: string, limit: string, offset = 0) => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.post<SearchResponse>(
        `${apiUrl}/search`,
        buildNaturalSearchPayload(naturalQuery, limit, offset),
        { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` } },
      );
      setSearchResponse(response.data);
      setOriginSearchId(response.data.search_id);
      setResults(response.data.results ?? []);
    } catch (error: any) {
      const apiMessage = error.response?.data?.message;
      setIsError(true);
      setMessage(apiMessage || error.message || "Nie udało się wykonać wyszukiwania.");
    } finally {
      setIsLoading(false);
    }
  }, [apiKey, apiUrl]);

  const handleExplicitSearch = React.useCallback(async (
    criteria: SearchInterpretation, limit: string, offset = 0,
  ) => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.post<SearchResponse>(`${apiUrl}/search`,
        { ...buildExplicitSearchPayload(criteria, limit), ...(offset ? { offset } : {}) }, {
          headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` },
        });
      setSearchResponse(response.data);
      setResults(response.data.results ?? []);
      return true;
    } catch (error: any) {
      setIsError(true);
      setMessage(error.response?.data?.message || error.message || "Nie udało się wykonać wyszukiwania.");
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [apiKey, apiUrl]);

  const sendFeedback = React.useCallback(async (
    verdict: "correct" | "partially_correct" | "incorrect",
    correctedQuery?: SearchInterpretation,
  ) => {
    if (originSearchId == null) return false;
    try {
      await axios.post(`${apiUrl}/search/${originSearchId}/feedback`, {
        verdict,
        ...(correctedQuery ? { corrected_query: correctedQuery } : {}),
      }, { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` } });
      setFeedbackMessage(verdict === "correct" ? "Dziękujemy za potwierdzenie."
        : verdict === "incorrect" ? "Dziękujemy — zapisano błąd interpretacji."
          : "Zapisano poprawioną interpretację.");
      return true;
    } catch {
      setFeedbackMessage("Nie udało się zapisać feedbacku.");
      return false;
    }
  }, [apiKey, apiUrl, originSearchId]);

  const clearSearch = React.useCallback(() => {
    setResults(null);
    setSearchResponse(null);
    setMessage("");
    setIsError(false);
    setOriginSearchId(null);
    setFeedbackMessage("");
  }, []);

  return {
    isError, isLoading, results, searchResponse, message,
    originSearchId, feedbackMessage,
    handleSearch, handleExplicitSearch, sendFeedback, clearSearch,
  };
};
