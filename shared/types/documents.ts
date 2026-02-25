export interface WebDocument {
  id: string;
  author: string;
  source: string;
  language: string;
  url: string;
  tags: string;
  title: string;
  summary: string;
  text: string;
  text_md: string;
  text_english: string;
  document_type: string;
  document_state: string;
  document_state_error: string;
  chapter_list: string;
  note: string;
  next_id: number | null;
  previous_id: number | null;
  next_type: string;
  previous_type: string;
}

export const emptyDocument: WebDocument = {
  id: "",
  author: "",
  source: "",
  language: "",
  url: "",
  tags: "",
  title: "",
  summary: "",
  text: "",
  text_md: "",
  text_english: "",
  document_type: "",
  document_state: "",
  document_state_error: "",
  chapter_list: "",
  note: "",
  next_id: null,
  previous_id: null,
  next_type: "",
  previous_type: "",
};

export interface SearchResult {
  id: number;
  text: string;
  similarity: number;
  website_id: number;
  url: string;
}

export interface ListItem {
  id: number;
  title: string;
  url: string;
  document_state: string;
  document_type: string;
}
