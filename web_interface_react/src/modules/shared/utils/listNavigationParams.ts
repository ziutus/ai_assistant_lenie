/** Translate the shareable list URL to the neighbors API contract. */
export function listNavigationParams(context: string, documentId: string): URLSearchParams | null {
  if (!context) return null;
  const params = new URLSearchParams(context);
  if (params.get("type") === "" || params.get("status") === "") return null;
  if (params.has("status")) params.set("processing_status", params.get("status")!);
  if (params.get("obsidian") === "missing") params.set("only_missing_obsidian_notes", "true");
  if (params.get("obsidian") === "has") params.set("only_has_obsidian_notes", "true");
  params.set("document_id", documentId);
  return params;
}
