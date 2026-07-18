import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";

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
}

export const buildNaturalSearchPayload = (naturalQuery: string, limit: string) => ({
  natural_query: naturalQuery.trim(),
  limit: Number(limit),
});

export const useSearch = () => {
  const [message, setMessage] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isError, setIsError] = React.useState(false);
  const [results, setResults] = React.useState<any[] | null>(null);
  const [searchResponse, setSearchResponse] = React.useState<SearchResponse | null>(null);
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const handleSearch = React.useCallback(async (naturalQuery: string, limit: string) => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.post<SearchResponse>(
        `${apiUrl}/search`,
        buildNaturalSearchPayload(naturalQuery, limit),
        { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` } },
      );
      setSearchResponse(response.data);
      setResults(response.data.results ?? []);
    } catch (error: any) {
      const apiMessage = error.response?.data?.message;
      setIsError(true);
      setMessage(apiMessage || error.message || "Nie udało się wykonać wyszukiwania.");
    } finally {
      setIsLoading(false);
    }
  }, [apiKey, apiUrl]);

  const clearSearch = React.useCallback(() => {
    setResults(null);
    setSearchResponse(null);
    setMessage("");
    setIsError(false);
  }, []);

  return {
    isError, isLoading, results, searchResponse, message,
    handleSearch, clearSearch,
  };
};
