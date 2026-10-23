import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import GithubRate, { type GithubRateInfo } from "./githubRate";

const rate = (overrides: Partial<GithubRateInfo> = {}): GithubRateInfo => ({
  limit: 5000, remaining: 4987, reset: "2026-10-23T17:33:50+00:00", authenticated: true, ...overrides,
});

describe("GithubRate", () => {
  afterEach(() => cleanup());

  it("shows what is left of the hourly quota", () => {
    render(<GithubRate rate={rate()} />);
    const text = screen.getByRole("status").textContent ?? "";
    expect(text).toContain("pozostało");
    expect(text).toMatch(/4\s?987/);
    expect(text).toMatch(/5\s?000/);
    expect(text).toContain("reset o");
    expect(text).not.toContain("bez tokenu");
    expect(text).not.toContain("na wyczerpaniu");
  });

  it("warns when the quota is nearly used up", () => {
    render(<GithubRate rate={rate({ remaining: 300 })} />);
    expect(screen.getByRole("status").textContent).toContain("limit na wyczerpaniu");
  });

  it("says so when no token is configured", () => {
    render(<GithubRate rate={rate({ limit: 60, remaining: 41, authenticated: false })} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("bez tokenu");
    expect(status.getAttribute("title")).toContain("GITHUB_TOKEN");
  });

  it("is honest about missing data and renders nothing before it loads", () => {
    const { container, rerender } = render(<GithubRate rate={undefined} />);
    expect(container.textContent).toBe("");
    rerender(<GithubRate rate={null} />);
    expect(container.textContent).toContain("brak danych o limicie");
  });
});
