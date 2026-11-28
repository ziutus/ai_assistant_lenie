export type Endpoint = { type: "person" | "organization" | "country"; id?: number; slug?: string; name?: string };
export type Relation = {
  id: number; subject: Endpoint; object: Endpoint; other: Endpoint; direction: "incoming" | "outgoing";
  relation: string; label: string; title: string | null; valid_from: string | null; valid_to: string | null;
  status: "proposed" | "confirmed" | "rejected"; detection_method: string | null; source: string; editable: boolean;
  evidence: { id: number; document_id: number | null; document_title: string | null; quote: string | null; claim: string | null; source_url: string | null }[];
};
export type Vocabulary = { value: string; label: string; inverse_label: string; pairs: { subject: Endpoint["type"]; object: Endpoint["type"] }[]; symmetric: boolean };
export const errorText = (error: unknown) => {
  const e = error as { response?: { status?: number; data?: { message?: string } }; message?: string };
  return e.response?.status === 409 ? "Dokument jest zajęty. Spróbuj ponownie po zakończeniu bieżącej operacji." : e.response?.data?.message ?? e.message ?? "Nie udało się wykonać operacji.";
};
export const safeUrl = (value: string | null) => {
  try { const url = new URL(value ?? ""); return ["http:", "https:"].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
};
export type ApiProps = { apiUrl: string; apiKey: string };
