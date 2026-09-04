import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderInline, renderMarkdown } from "./read";

const show = (nodes: React.ReactNode) =>
  render(<MemoryRouter><p>{nodes}</p></MemoryRouter>);

describe("renderInline — links", () => {
  it("linkifies a bare https:// URL", () => {
    show(renderInline("zob. https://training.linuxfoundation.org/resources/kubestronaut-program/"));
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe(
      "https://training.linuxfoundation.org/resources/kubestronaut-program/",
    );
  });

  it("keeps trailing sentence punctuation outside the bare URL link", () => {
    show(renderInline("patrz https://example.com/x."));
    expect(screen.getByRole("link").getAttribute("href")).toBe("https://example.com/x");
    expect(screen.getByRole("link").parentElement?.textContent).toBe("patrz https://example.com/x.");
  });

  it("renders a [label](url) markdown link with the label as text", () => {
    show(renderInline("[dokumentacja](https://example.com/docs)"));
    const link = screen.getByRole("link", { name: "dokumentacja" });
    expect(link.getAttribute("href")).toBe("https://example.com/docs");
  });

  it("still renders a parenthesized (https://…) URL", () => {
    show(renderInline("Good Times (https://example.com/gt)"));
    expect(screen.getByRole("link").getAttribute("href")).toBe("https://example.com/gt");
  });
});

describe("renderInline — nested inline inside bold/italic", () => {
  it("resolves a wikilink wrapped in **bold** instead of showing raw [[ ]]", () => {
    const wikiLinks = new Map<string, number>([["kubestronaut program", 9999]]);
    show(renderInline("wymagany do **[[Kubestronaut Program]]**", undefined, undefined, undefined, wikiLinks));
    const link = screen.getByRole("link", { name: "Kubestronaut Program" });
    expect(link.getAttribute("href")).toBe("/read/9999");
    expect(screen.queryByText(/\[\[/)).toBeNull();
  });

  it("linkifies a bare URL inside *italic*", () => {
    show(renderInline("*zob. https://example.com/i*"));
    expect(screen.getByRole("link").getAttribute("href")).toBe("https://example.com/i");
  });
});

describe("renderMarkdown — heading not sharing a blank line with the text below", () => {
  it("keeps a follow-on line out of the <h_> and renders it as its own block", () => {
    const { container } = render(
      <MemoryRouter>
        <div>{renderMarkdown("## Płatne szkolenia\nhttps://learn.kodekloud.com/x", [])}</div>
      </MemoryRouter>,
    );
    const h = container.querySelector("h3");
    expect(h?.textContent).toBe("Płatne szkolenia");
    expect(h?.querySelector("a")).toBeNull();
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("https://learn.kodekloud.com/x");
    expect(h?.contains(link)).toBe(false);
  });
});
