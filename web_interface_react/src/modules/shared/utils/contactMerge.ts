export const MERGE_FIELDS = [
  ["first_name", "Imię"], ["last_name", "Nazwisko"], ["gender", "Płeć"], ["display_label", "Nazwa robocza"],
  ["phone_number", "Główny telefon"], ["email", "Główny e-mail"], ["company", "Firma"], ["position", "Stanowisko"],
  ["current_city", "Miejscowość"], ["hometown", "Miejscowość rodzinna"], ["birthday", "Data urodzenia"],
  ["birthday_month", "Miesiąc urodzenia"], ["birthday_day", "Dzień urodzenia"], ["pesel", "PESEL"],
  ["notes", "Notatki"], ["private_notes", "Notatki prywatne"], ["category_id", "Kategoria"],
  ["languages", "Języki"], ["nationality", "Obywatelstwo"], ["photo_storage_key", "Zdjęcie"],
  ["photo_thumbnail_storage_key", "Miniatura zdjęcia"],
] as const;
export type Field = typeof MERGE_FIELDS[number][0];
export type Choices = Record<Field, "primary" | "duplicate">;

export const isEmpty = (value: unknown) => value == null || value === "" || (Array.isArray(value) && value.length === 0);

export const defaultChoices = (primary: Record<string, unknown>, duplicate: Record<string, unknown>): Choices =>
  Object.fromEntries(MERGE_FIELDS.map(([field]) => [field,
    isEmpty(primary[field]) && !isEmpty(duplicate[field]) ? "duplicate" : "primary",
  ])) as Choices;
