/** Kinds and roles an information source of a document can have (mirrors `document_event_sources.SOURCE_TYPES` and
 *  `information_provenance.ALLOWED_ROLES` on the server). */
export const SOURCE_TYPES: { code: string; label: string }[] = [
  { code: "study", label: "badanie / artykuł naukowy" },
  { code: "book", label: "książka" },
  { code: "report", label: "raport" },
  { code: "institution", label: "instytucja" },
  { code: "agency", label: "agencja" },
  { code: "newspaper", label: "gazeta" },
  { code: "portal", label: "portal" },
  { code: "database", label: "baza danych" },
  { code: "other", label: "inne" },
];

export const SOURCE_ROLES: { code: string; label: string }[] = [
  { code: "cited", label: "cytowane w tekście" },
  { code: "data_source", label: "źródło danych" },
  { code: "original_reporting", label: "pierwotne ustalenia" },
  { code: "republication", label: "przedruk" },
];

export const sourceTypeLabel = (code: string | null | undefined): string =>
  SOURCE_TYPES.find((type) => type.code === code)?.label ?? (code || "źródło");

export const sourceRoleLabel = (code: string): string =>
  SOURCE_ROLES.find((role) => role.code === code)?.label ?? code;
