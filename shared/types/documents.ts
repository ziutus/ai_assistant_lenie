export interface Document {
  id: string;
  byline: string;
  source: string;
  language: string;
  url: string;
  canonical_url: string;
  tags: string;
  search_terms: string;
  title: string;
  summary: string;
  text: string;
  text_md: string;
  document_type: string;
  processing_status: string;
  processing_error_code: string;
  chapter_list: string;
  email_sender: string;
  note: string;
  next_id: number | null;
  previous_id: number | null;
  next_type: string;
  previous_type: string;
  groups?: ContentGroup[];
}

export interface ContentGroup {
  id: number;
  name: string;
  kind: "topic" | "priority";
  priority_rank: number | null;
  archived_at?: string | null;
  source?: string;
}

export interface ContentGroupSuggestion {
  id: number;
  run_id: number;
  group_id: number;
  confidence: number;
  reason: string | null;
  status: "pending" | "accepted" | "dismissed" | "reverted";
  membership_created: boolean;
  decided_by_user_id: number | null;
  decided_at: string | null;
}

export const emptyDocument: Document = {
  id: "",
  byline: "",
  source: "",
  language: "",
  url: "",
  canonical_url: "",
  tags: "",
  search_terms: "",
  title: "",
  summary: "",
  text: "",
  text_md: "",
  document_type: "",
  processing_status: "",
  processing_error_code: "",
  chapter_list: "",
  email_sender: "",
  note: "",
  next_id: null,
  previous_id: null,
  next_type: "",
  previous_type: "",
};

// Discovery source lookup row (backend table `discovery_sources`, GET /sources).
// `count` = number of web_documents using this source (via discovery_source_id).
export interface Source {
  id: number;
  name: string;
  description: string | null;
  url: string | null;
  is_active: boolean;
  count: number;
}

export interface SearchResult {
  id: number;
  text: string;
  similarity: number;
  document_id: number;
  url: string;
  chunk_id: number | null;
  obsidian_note_paths: string[];
}

export interface ListItem {
  id: number;
  title: string;
  url: string;
  processing_status: string;
  document_type: string;
  groups?: ContentGroup[];
  effective_priority_rank?: number | null;
}
