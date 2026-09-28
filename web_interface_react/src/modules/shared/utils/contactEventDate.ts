export function formatEventDateRange(start: string, end?: string | null): string {
  const year = start.slice(0, 4);
  const month = start.slice(5, 7);
  const day = start.slice(8, 10);
  const single = `${day}.${month}.${year}`;
  if (!end || end === start) return single;
  const endYear = end.slice(0, 4);
  const endMonth = end.slice(5, 7);
  const endDay = end.slice(8, 10);
  if (year !== endYear) return `${single}-${endDay}.${endMonth}.${endYear}`;
  if (month !== endMonth) return `${day}.${month}-${endDay}.${endMonth}.${year}`;
  return `${day}-${endDay}.${month}.${year}`;
}
