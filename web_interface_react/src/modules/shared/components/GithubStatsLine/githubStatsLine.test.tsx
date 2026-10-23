import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import GithubStatsLine, { type GithubStats } from "./githubStatsLine";

const stats = (overrides: Partial<GithubStats> = {}): GithubStats => ({
  full_name: "tt-rss/tt-rss", status: "ok", stars: 868, forks: 88, watchers: 40, open_issues: 5, language: "PHP",
  license: "GPL-3.0", archived: false, pushed_at: "2026-10-22T15:19:29+00:00", fetched_at: "2026-10-23T09:00:00+00:00",
  ...overrides,
});

describe("GithubStatsLine", () => {
  afterEach(() => cleanup());

  it("shows a single repository without a sum or breakdown", () => {
    render(<GithubStatsLine stats={stats({ repositories: [stats()] })} />);
    expect(screen.getByLabelText("gwiazdki").textContent).toContain("868");
    expect(screen.queryByLabelText("suma")).toBeNull();
    expect(screen.queryByText(/pokaż składniki sumy/)).toBeNull();
  });

  it("marks a sum of several repositories and lists each one with its provider", () => {
    const github = stats({ provider: "github", host: "github.com", url: "https://github.com/tt-rss/tt-rss" });
    const gitlab = stats({
      full_name: "gitlab.example.org/tt/mirror", provider: "gitlab", host: "gitlab.example.org", stars: 12, forks: 2,
      open_issues: 1, url: "https://gitlab.example.org/tt/mirror",
    });
    render(<GithubStatsLine stats={stats({ stars: 880, forks: 90, repositories: [github, gitlab] })} />);

    expect(screen.getByLabelText("suma")).toBeTruthy();
    expect(screen.getByLabelText("gwiazdki").textContent).toContain("880");
    expect(screen.getByText(/Σ 2 repozytoria/)).toBeTruthy();
    expect(screen.getByText("GitHub")).toBeTruthy();
    expect(screen.getByText("GitLab")).toBeTruthy();
    expect(screen.getByRole("link", { name: "gitlab.example.org/tt/mirror" }).getAttribute("href")).toBe("https://gitlab.example.org/tt/mirror");
  });

  it("explains a repository that has no numbers (moved or retired)", () => {
    const moved = stats({
      full_name: "gitlab.tt-rss.org/tt-rss/tt-rss", provider: "gitlab", stars: null, forks: null, open_issues: null,
      status: "not_found", url: "https://gitlab.tt-rss.org/tt-rss/tt-rss",
    });
    render(<GithubStatsLine stats={stats({ repositories: [stats({ provider: "github" }), moved] })} />);
    expect(screen.getByText(/przeniesione/)).toBeTruthy();
  });
});
