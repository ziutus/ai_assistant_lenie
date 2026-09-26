/**
 * Dates known only to the year or the month ("lives there since 2016").
 * Wire format (same as the backend, library/partial_dates.py): "2016", "2016-03" or "2016-03-05".
 * Shown and typed the Polish way: "2016", "03.2016", "05.03.2016".
 */

const WIRE = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/;

export function partialDateToDisplay(value: string | null | undefined): string {
  const match = value ? WIRE.exec(value) : null;
  if (!match) return value ?? "";
  const [, year, month, day] = match;
  if (day) return `${day}.${month}.${year}`;
  if (month) return `${month}.${year}`;
  return year;
}

const pad = (n: string) => n.padStart(2, "0");

/**
 * What the user typed -> wire value. `null` = empty (clear the date), `undefined` = not a valid date.
 * Accepts 2016, 3.2016 / 03-2016 / 03/2016, 5.3.2016 / 05.03.2016 and the ISO forms.
 */
export function parsePartialDateInput(text: string): string | null | undefined {
  const value = text.trim();
  if (!value) return null;
  let year: string, month: string | undefined, day: string | undefined;
  let m: RegExpExecArray | null;
  if ((m = /^(\d{4})$/.exec(value))) {
    year = m[1];
  } else if ((m = /^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$/.exec(value))) {
    [, year, month, day] = m;
  } else if ((m = /^(\d{1,2})[./-](\d{4})$/.exec(value))) {
    [, month, year] = m;
  } else if ((m = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/.exec(value))) {
    [, day, month, year] = m;
  } else {
    return undefined;
  }
  if (Number(year) < 1000) return undefined;
  if (month !== undefined) {
    if (Number(month) < 1 || Number(month) > 12) return undefined;
    if (day !== undefined) {
      const date = new Date(Number(year), Number(month) - 1, Number(day));
      if (date.getFullYear() !== Number(year) || date.getMonth() !== Number(month) - 1 || date.getDate() !== Number(day)) {
        return undefined;
      }
      return `${year}-${pad(month)}-${pad(day)}`;
    }
    return `${year}-${pad(month)}`;
  }
  return year;
}
