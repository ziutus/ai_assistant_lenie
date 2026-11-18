import axios from "axios";
import type { ModelOption } from "../../utils/modelDetails";
import type { WorldEvent } from "./worldEventCard";

export interface Credits {
  serper: { credits_left: number | null; error?: string };
  firecrawl: { remaining: number | null; plan: number | null; error?: string };
}
export interface ModelConfig { default_model: string | null; saved: boolean; models: ModelOption[] }
export interface Estimate {
  serper_credits: number; firecrawl_credits: number;
  llm: { model: string; est_input_tokens: number; est_output_tokens: number; est_cost_usd: string | null };
}
export type Proposal = Partial<Pick<WorldEvent, "description" | "kind" | "event_date" | "event_date_end" | "is_ongoing">> & {
  countries: string[]; organizations: string[]; sources_used: { url: string; quote: string }[];
};
export type EnrichStep = "wikipedia" | "web";
export interface WikipediaResult { found: boolean; lang: string | null; title: string | null; url: string | null }
export interface EnrichResult {
  source_step: EnrichStep; wikipedia: WikipediaResult; suggest_web?: boolean;
  proposal: Proposal | null; sources: { title: string; url: string; snippet: string }[];
  rejected: Record<string, number>; model: string;
  usage: { serper_credits: number; firecrawl_credits: number;
    llm: { llm_cost_amount: string | null; llm_cost_currency: string | null } };
}
export const webEnrichApi = (base: string, headers: Record<string, string>) => ({
  models: async () => (await axios.get<ModelConfig>(`${base}/geo_events/web_enrich/model`, { headers })).data,
  saveModel: async (model: string) => (await axios.put<ModelConfig>(`${base}/geo_events/web_enrich/model`, { model }, { headers })).data,
  credits: async () => (await axios.get<Credits>(`${base}/web_search/credits`, { headers })).data,
  estimate: async (id: number, model: string, scrape_pages: number, step: EnrichStep = "wikipedia", with_wikipedia = false) =>
    (await axios.post<Estimate>(`${base}/geo_events/${id}/web_enrich/estimate`, { model, scrape_pages, step, with_wikipedia }, { headers })).data,
  enrich: async (id: number, model: string, scrape_pages: number, step: EnrichStep = "wikipedia", with_wikipedia = false) =>
    (await axios.post<EnrichResult>(`${base}/geo_events/${id}/web_enrich`, { model, scrape_pages, step, with_wikipedia }, { headers })).data,
  patch: async (id: number, changes: Record<string, unknown>) =>
    axios.patch(`${base}/geo_events/${id}`, changes, { headers }),
  participant: async (id: number, type: string, ref: string) =>
    axios.post(`${base}/geo_events/${id}/participants`, { type, ref, role: "subject" }, { headers }),
});
