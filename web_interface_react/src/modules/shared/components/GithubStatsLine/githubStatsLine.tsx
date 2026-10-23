export type GithubStats = {
  full_name: string; status: "ok" | "not_found";
  stars: number | null; forks: number | null; watchers: number | null; open_issues: number | null;
  language: string | null; license: string | null; archived: boolean;
  pushed_at: string | null; fetched_at: string | null;
  /** The repository's own About text and topics; absent in responses of older backends. */
  description?: string | null; topics?: string[];
};

const countFormat = new Intl.NumberFormat("pl-PL");
const formatCount = (value: number | null) => value === null ? "—" : countFormat.format(value);
const INACTIVE_AFTER_MS = 365 * 24 * 60 * 60 * 1000;

/** One-line summary of a repository's public GitHub numbers (shared by the tool radar and the tool catalog). */
export default function GithubStatsLine({ stats }: { stats: GithubStats }) {
  const pushed = stats.pushed_at ? Date.parse(stats.pushed_at) : NaN;
  const inactive = !Number.isNaN(pushed) && Date.now() - pushed > INACTIVE_AFTER_MS;
  const badge = (text: string, background: string, color: string) =>
    <span style={{ marginLeft: 6, background, color, borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{text}</span>;
  return <div title={`Dane z GitHuba (${stats.full_name}), pobrane ${stats.fetched_at ? stats.fetched_at.slice(0, 10) : "—"}`}
    style={{ color: "#475569", fontSize: ".85rem", margin: "6px 0" }}>
    <span aria-label="gwiazdki">★ {formatCount(stats.stars)}</span>
    {" · "}<span aria-label="forki">⑂ {formatCount(stats.forks)}</span>
    {" · "}<span aria-label="obserwujący">👁 {formatCount(stats.watchers)}</span>
    {" · "}<span aria-label="otwarte issues">issues {formatCount(stats.open_issues)}</span>
    {stats.language && <>{" · "}{stats.language}</>}
    {stats.license && <>{" · "}{stats.license}</>}
    {stats.pushed_at && <>{" · "}ostatni push {stats.pushed_at.slice(0, 10)}</>}
    {stats.status === "not_found" && badge("repozytorium nie istnieje", "#fee2e2", "#991b1b")}
    {stats.archived && badge("zarchiwizowane", "#fef3c7", "#92400e")}
    {inactive && !stats.archived && badge("brak aktywności od ponad roku", "#fef3c7", "#92400e")}
  </div>;
}
