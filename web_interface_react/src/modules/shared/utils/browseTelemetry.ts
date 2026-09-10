export type CriteriaOrigin = "default" | "remembered" | "url" | "manual" | "ai";
export type BrowseAction = "initial_load" | "submit" | "filter_change" | "sort_change" | "page_change"
  | "page_size_change" | "clear" | "refresh" | "correction";
export interface BrowseContext {
  session_id: string;
  browse_id: string;
  event_id: string;
  action: BrowseAction;
  requested_mode: string;
  changed_fields: string[];
  criteria_origin: Record<string, CriteriaOrigin>;
}

// getRandomValues also works on the NAS's HTTP origin, where randomUUID may be unavailable.
export function browseUuid(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

let fallbackSession: string | undefined;
function sessionId(): string {
  try {
    let id = sessionStorage.getItem("lenie_browse_session");
    if (!id) { id = browseUuid(); sessionStorage.setItem("lenie_browse_session", id); }
    return id;
  } catch {
    return fallbackSession ??= browseUuid();
  }
}

export class BrowseTelemetry {
  browseId = browseUuid();
  origins: Record<string, CriteriaOrigin>;
  pending = new Set<string>();
  constructor(origins: Record<string, CriteriaOrigin> = {}) { this.origins = origins; }
  manual(...fields: string[]) {
    fields.forEach(field => { this.origins[field] = "manual"; this.pending.add(field); });
  }
  next(action: BrowseAction, mode: string, consumeChanges = true): BrowseContext {
    if (consumeChanges && ["page_change", "refresh"].includes(action) && this.pending.size) {
      action = this.pending.has("sort") ? "sort_change" : "filter_change";
    }
    if (!["page_change", "refresh", "page_size_change", "correction"].includes(action)) this.browseId = browseUuid();
    const context = {
      session_id: sessionId(), browse_id: this.browseId, event_id: browseUuid(), action,
      requested_mode: mode, changed_fields: consumeChanges ? [...this.pending] : [], criteria_origin: { ...this.origins },
    };
    if (consumeChanges) this.pending.clear();
    return context;
  }
}

export function listOrigins(params: URLSearchParams): Record<string, CriteriaOrigin> {
  let saved: Record<string, unknown> = {};
  try { saved = JSON.parse(localStorage.getItem("lenie_listFilters") || "{}"); } catch { /* defaults */ }
  const mapping: Record<string, [string, string?]> = {
    document_type: ["type", "documentType"], processing_status: ["status", "documentState"],
    query: ["q", "searchText"], requested_mode: ["mode", "searchType"],
    only_missing_obsidian_notes: ["obsidian", "obsidianFilter"], only_has_obsidian_notes: ["obsidian", "obsidianFilter"],
    without_embedding: ["without_embedding"], topic_group_ids: ["topic_group_ids"],
    topic_filter_active: ["topic_filter"], include_without_topics: ["without_topics"],
    topic_match: ["topic_match"], priority_group_id: ["priority_group_id"], without_priority: ["without_priority"],
    sort: ["sort"], page_size: ["page_size"],
  };
  return Object.fromEntries(Object.entries(mapping).map(([field, [url, storage]]) => [field,
    (field !== "requested_mode" && (params.has(url) || (field === "topic_filter_active"
      && (params.has("topic_group_ids") || params.has("without_topics"))))) ? "url" : storage && saved && Object.prototype.hasOwnProperty.call(saved, storage) ? "remembered" : "default",
  ]));
}

export function listTelemetryParams(context?: BrowseContext) {
  if (!context) return {};
  return Object.fromEntries(Object.entries(context).map(([key, value]) => [
    `_tel_${key}`, typeof value === "object" ? JSON.stringify(value) : value,
  ]));
}
