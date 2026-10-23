import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ToolLinksEditor from "./toolLinksEditor";
import { isRepositoryUrl, linksToText, textToLinks } from "../ToolCard/toolCardParts";

describe("link text helpers", () => {
  it("round-trips 'Label | address' lines and bare addresses", () => {
    const links = [{ url: "https://example.com/pricing", label: "Cennik" }, { url: "https://github.com/a/b", label: "" }];
    expect(linksToText(links)).toBe("Cennik | https://example.com/pricing\nhttps://github.com/a/b");
    expect(textToLinks(`${linksToText(links)}\n\n  `)).toEqual(links);
  });

  it.each([
    ["https://github.com/tt-rss/tt-rss", true], ["github.com/a/b", true], ["https://github.com/topics", false],
    ["https://gitlab.com/group/sub/project", true], ["https://gitlab.tt-rss.org/tt-rss/tt-rss", true],
    ["https://gitlab.com/explore/projects", false], ["https://notgitlab.com/a/b", false], ["https://tt-rss.org", false],
    ["", false], [null, false],
  ])("isRepositoryUrl(%s) is %s", (url, expected) => {
    expect(isRepositoryUrl(url as string | null)).toBe(expected);
  });
});

describe("ToolLinksEditor", () => {
  afterEach(() => cleanup());

  it("shows the homepage first, then the extra links with a label or their host", () => {
    render(<ToolLinksEditor homepageUrl="https://tt-rss.org" disabled={false} onSave={vi.fn()}
      links={[{ url: "https://example.com/pricing", label: "Cennik" }, { url: "https://github.com/tt-rss/tt-rss", label: "" },
        { url: "https://tt-rss.org", label: "duplikat strony" }]} />);
    const anchors = screen.getAllByRole("link").map(anchor => anchor.textContent);
    expect(anchors).toEqual(["Strona narzędzia", "Cennik", "github.com"]);
  });

  it("sends nothing until 'Zapisz linki' and then the parsed list", () => {
    const onSave = vi.fn();
    render(<ToolLinksEditor homepageUrl={null} links={[]} disabled={false} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: /Dodaj linki/ }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Cennik | https://example.com/pricing\nhttps://gitlab.com/g/p" } });
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Zapisz linki" }));
    expect(onSave).toHaveBeenCalledWith([
      { label: "Cennik", url: "https://example.com/pricing" }, { label: "", url: "https://gitlab.com/g/p" },
    ]);
  });

  it("cancel leaves the list untouched", () => {
    const onSave = vi.fn();
    render(<ToolLinksEditor homepageUrl="https://tt-rss.org" links={[{ url: "https://a.b", label: "A" }]} disabled={false} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: /Edytuj linki/ }));
    fireEvent.click(screen.getByRole("button", { name: "Anuluj" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "A" })).toBeTruthy();
  });
});
