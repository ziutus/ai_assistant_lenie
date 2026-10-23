export type GithubStats = {
  full_name: string; status: "ok" | "not_found";
  stars: number | null; forks: number | null; watchers: number | null; open_issues: number | null;
  language: string | null; license: string | null; archived: boolean;
  pushed_at: string | null; fetched_at: string | null;
  /** The repository's own About text and topics; absent in responses of older backends. */
  description?: string | null; topics?: string[];
  /** Where the numbers come from; absent in responses of older backends (then GitHub). */
  provider?: "github" | "gitlab"; host?: string; url?: string;
  /** Per-repository numbers when the entry has several repositories: the fields above are their sum. */
  repositories?: GithubStats[];
};

const countFormat = new Intl.NumberFormat("pl-PL");
const formatCount = (value: number | null) => value === null ? "—" : countFormat.format(value);
const INACTIVE_AFTER_MS = 365 * 24 * 60 * 60 * 1000;
const providerName = (stats: GithubStats) => stats.provider === "gitlab" ? "GitLab" : "GitHub";
const repositoryWord = (count: number) => count < 5 ? "repozytoria" : "repozytoriów";

/** The per-repository numbers behind a sum, e.g. a GitLab original and its GitHub mirror. */
export function RepositoryBreakdown({ repositories }: { repositories: GithubStats[] }) {
  return <details style={{ margin: "2px 0 6px", fontSize: ".8rem", color: "#64748b" }}>
    <summary style={{ cursor: "pointer" }}>Σ {repositories.length} {repositoryWord(repositories.length)} — pokaż składniki sumy</summary>
    <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
      {repositories.map(repository => <li key={repository.url ?? repository.full_name}>
        <strong>{providerName(repository)}</strong>{" "}
        {repository.url ? <a href={repository.url} target="_blank" rel="noreferrer">{repository.full_name}</a> : repository.full_name}
        {": "}★ {formatCount(repository.stars)} · ⑂ {formatCount(repository.forks)} · issues {formatCount(repository.open_issues)}
        {repository.pushed_at && <>{" · "}push {repository.pushed_at.slice(0, 10)}</>}
        {repository.status === "not_found" && <> · <em>brak danych (repozytorium nie istnieje albo zostało przeniesione)</em></>}
      </li>)}
    </ul>
  </details>;
}

/** One-line summary of a repository's public GitHub/GitLab numbers (shared by the tool radar and the tool catalog). */
export default function GithubStatsLine({ stats }: { stats: GithubStats }) {
  const pushed = stats.pushed_at ? Date.parse(stats.pushed_at) : NaN;
  const inactive = !Number.isNaN(pushed) && Date.now() - pushed > INACTIVE_AFTER_MS;
  const repositories = stats.repositories ?? [];
  const several = repositories.length > 1;
  const providers = Array.from(new Set(repositories.map(providerName)));
  const source = several ? providers.join(" + ") : providerName(stats);
  const badge = (text: string, background: string, color: string) =>
    <span style={{ marginLeft: 6, background, color, borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{text}</span>;
  return <>
    <div title={`Dane z: ${source} (${several ? `suma ${repositories.length} ${repositoryWord(repositories.length)}` : stats.full_name}), pobrane ${stats.fetched_at ? stats.fetched_at.slice(0, 10) : "—"}`}
      style={{ color: "#475569", fontSize: ".85rem", margin: "6px 0" }}>
      {several && <span aria-label="suma" style={{ marginRight: 6, fontWeight: 600 }}>Σ</span>}
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
    </div>
    {several && <RepositoryBreakdown repositories={repositories} />}
  </>;
}
