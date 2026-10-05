/** Context and URLs keep strings: ALL = unrestricted, empty = no results. */
export const filterValues = (value: string, options: string[]): string[] =>
  value === "ALL" ? options : [...new Set(value.split(",").map(part => part.trim()).filter(Boolean))];

export const filterCsv = (values: string[], options: string[]): string => {
  const unique = [...new Set(values)];
  return options.length > 0 && unique.length === options.length && options.every(value => unique.includes(value))
    ? "ALL" : unique.join(",");
};
