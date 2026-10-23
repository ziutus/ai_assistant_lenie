import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import GithubAbout, { toTag } from "./githubAbout";
import type { GithubStats } from "../GithubStatsLine/githubStatsLine";

const stats = (overrides: Partial<GithubStats> = {}): GithubStats => ({
  full_name: "anchore/grype", status: "ok", stars: 1, forks: 1, watchers: 1, open_issues: 1, language: "Go", license: "Apache-2.0",
  archived: false, pushed_at: null, fetched_at: null,
  description: "A vulnerability scanner for container images and filesystems", topics: ["containers", "SBOM", "vulnerability scanner"],
  ...overrides,
});

const renderAbout = (props: Partial<React.ComponentProps<typeof GithubAbout>> = {}) => {
  const onUseDescription = vi.fn();
  const onAddTags = vi.fn();
  render(<GithubAbout stats={stats()} ownDescription={null} tags={[]} disabled={false}
    onUseDescription={onUseDescription} onAddTags={onAddTags} {...props} />);
  return { onUseDescription, onAddTags };
};

describe("GithubAbout", () => {
  afterEach(() => cleanup());

  it("normalises topics like stored tags", () => {
    expect(toTag(" Vulnerability  Scanner ")).toBe("vulnerability-scanner");
  });

  it("offers the GitHub description when the entry has none, and writes nothing until clicked", () => {
    const { onUseDescription } = renderAbout();
    expect(onUseDescription).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Użyj jako opisu" }));
    expect(onUseDescription).toHaveBeenCalledWith("A vulnerability scanner for container images and filesystems");
  });

  it("offers a replacement when the descriptions differ and stays quiet when they match", () => {
    renderAbout({ ownDescription: "Skaner" });
    expect(screen.getByRole("button", { name: "Zastąp opis tym z GitHuba" })).toBeTruthy();
    cleanup();
    renderAbout({ ownDescription: "a vulnerability  SCANNER for container images and filesystems" });
    expect(screen.queryByRole("button", { name: /opis/i })).toBeNull();
    expect(screen.getByText("(taki sam jak Twój opis)")).toBeTruthy();
  });

  it("adds a single topic or all missing ones, skipping topics that are already tags", () => {
    const { onAddTags } = renderAbout({ tags: ["containers"] });
    expect(screen.getByTitle("Już jest wśród tagów").textContent).toContain("#containers");
    fireEvent.click(screen.getByRole("button", { name: "+ #sbom" }));
    expect(onAddTags).toHaveBeenLastCalledWith(["sbom"]);
    fireEvent.click(screen.getByRole("button", { name: "Dodaj wszystkie (2)" }));
    expect(onAddTags).toHaveBeenLastCalledWith(["sbom", "vulnerability-scanner"]);
  });

  it("renders nothing for a repository without description and topics", () => {
    const { container } = render(<GithubAbout stats={stats({ description: null, topics: [] })} ownDescription={null} tags={[]}
      disabled={false} onUseDescription={vi.fn()} onAddTags={vi.fn()} />);
    expect(container.textContent).toBe("");
  });

  describe("repository website", () => {
    const withWebsite = (props: Partial<React.ComponentProps<typeof GithubAbout>> = {}, overrides: Partial<GithubStats> = {}) => {
      const onUseHomepage = vi.fn();
      const onAddLink = vi.fn();
      const view = render(<GithubAbout stats={stats({ description: null, topics: [], homepage: "https://feedbin.com", ...overrides })}
        ownDescription={null} tags={[]} disabled={false} onUseDescription={vi.fn()} onAddTags={vi.fn()}
        homepageUrl="https://github.com/feedbin/feedbin" links={[]} onUseHomepage={onUseHomepage} onAddLink={onAddLink} {...props} />);
      return { onUseHomepage, onAddLink, ...view };
    };

    it("offers the website with two explicit buttons and writes nothing until one is clicked", () => {
      const { onUseHomepage, onAddLink } = withWebsite();
      expect(screen.getByRole("link", { name: "https://feedbin.com" })).toBeTruthy();
      expect(onUseHomepage).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: "Użyj jako strony" }));
      expect(onUseHomepage).toHaveBeenCalledWith("https://feedbin.com");
      fireEvent.click(screen.getByRole("button", { name: "Dodaj do linków" }));
      expect(onAddLink).toHaveBeenCalledWith("https://feedbin.com");
    });

    it("does not offer a website the entry already has, however it is spelled", () => {
      const { container } = withWebsite({ homepageUrl: "https://www.Feedbin.com/" });
      expect(container.textContent).toBe("");
      cleanup();
      const second = withWebsite({ links: [{ url: "feedbin.com" }] });
      expect(second.container.textContent).toBe("");
    });

    it("shows nothing when GitHub has no website", () => {
      const { container } = withWebsite({}, { homepage: null });
      expect(container.textContent).toBe("");
    });
  });
});
