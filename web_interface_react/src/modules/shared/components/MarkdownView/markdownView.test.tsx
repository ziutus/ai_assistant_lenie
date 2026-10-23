import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import MarkdownEditor from "./markdownEditor";
import MarkdownView, { parseBlocks } from "./markdownView";
import { cleanObsidianNote } from "./obsidianNote";

afterEach(cleanup);

// Trimmed copy of the real Obsidian note for tool #24 (the shape that exposed the formatting gaps).
const VAULT_NOTE = `---
tags:
  - wiedza/informatyka
---
## Hashicorp Vault

**Purpose:** Keeping secrets
**Type of application**: Saas, docker image
**Licence**: comercial / opensource
**homepage**: https://hub.docker.com/r/hashicorp/vault/tags
**Pricing type**: free tier / per usage
**pricing page**: https://www.hashicorp.com/en/pricing
Creating account by: github
### Key Points:

- you can have cloud version, docker version
- command line tool **hcp** is different one than for own hosted **vault**

# Pytania
* co oznacza, że w wersji community mamy lokalna HA?
  * zagnieżdżony punkt

### Important Commands:

\`\`\`bash
hcp profile init --vault-secrets
\`\`\`

\`\`\`
❯ hcp vault-secrets secrets list

Secret Name Created At
\`\`\`

# Additional Notes:





# Source of note

# Metadata
creation date: <% tp.file.creation_date() %>
modification date: <% tp.file.last_modified_date("dddd Do MMMM YYYY HH:mm:ss") %>
`;

describe("cleanObsidianNote", () => {
  it("drops front matter, fixed fields, the name heading and the template footer", () => {
    const { markdown, removed } = cleanObsidianNote(VAULT_NOTE, "HashiCorp Vault");
    expect(markdown).not.toMatch(/^---/);
    expect(markdown).not.toMatch(/Licence|Pricing type|pricing page|homepage|Purpose|Type of application/);
    expect(markdown).not.toMatch(/Metadata|<%|Source of note|Additional Notes/);
    expect(markdown.startsWith("Creating account by: github")).toBe(true);
    expect(markdown).toContain("### Key Points:");
    expect(markdown).toContain("hcp profile init --vault-secrets");
    expect(removed.join(" ")).toMatch(/front matter/);
    expect(removed.join(" ")).toMatch(/pola stałe/);
  });

  it("leaves a plain note alone and never touches fenced code", () => {
    expect(cleanObsidianNote("Zwykła notatka\n\n- punkt").removed).toEqual([]);
    const code = "```\n**Licence**: x\n```";
    expect(cleanObsidianNote(code).markdown).toBe(code);
  });
});

describe("parseBlocks", () => {
  it("does not swallow a heading or list that follows a paragraph without a blank line", () => {
    const kinds = parseBlocks("Creating account by: github\n### Key Points:\ntekst\n- a\n- b").map(block => block.kind);
    expect(kinds).toEqual(["paragraph", "heading", "paragraph", "list"]);
  });

  it("keeps blank lines inside a fenced block", () => {
    const [block] = parseBlocks("```bash\na\n\nb\n```");
    expect(block).toEqual({ kind: "code", lang: "bash", content: "a\n\nb" });
  });
});

describe("MarkdownView", () => {
  it("renders the Vault note body like Obsidian would", () => {
    const { markdown } = cleanObsidianNote(VAULT_NOTE, "HashiCorp Vault");
    const { container } = render(<MarkdownView text={markdown} />);
    expect(container.querySelectorAll("h5, h4, h3").length).toBeGreaterThanOrEqual(3);
    expect(container.querySelector("strong")?.textContent).toBe("hcp");
    expect(container.querySelectorAll("pre code").length).toBe(2);
    expect(container.textContent).toContain("❯ hcp vault-secrets secrets list");
    // `* item` with an indented `* child` becomes a nested list.
    expect(container.querySelector("ul ul li")?.textContent).toBe("zagnieżdżony punkt");
  });

  it("renders task lists, quotes, callouts, highlight, strikethrough and tables", () => {
    const { container } = render(<MarkdownView text={[
      "- [x] zrobione", "- [ ] do zrobienia", "", "> cytat", "", "> [!warning] Uwaga", "> treść ostrzeżenia", "",
      "==ważne== i ~~stare~~", "", "| A | B |", "|---|:-:|", "| 1 | 2 |",
    ].join("\n")} />);
    const boxes = Array.from(container.querySelectorAll<HTMLInputElement>("input[type=checkbox]"));
    expect(boxes.map(box => box.checked)).toEqual([true, false]);
    expect(container.querySelector("blockquote")?.textContent).toBe("cytat");
    expect(container.textContent).toContain("Uwaga");
    expect(container.textContent).toContain("treść ostrzeżenia");
    expect(container.querySelector("mark")?.textContent).toBe("ważne");
    expect(container.querySelector("del")?.textContent).toBe("stare");
    expect(container.querySelectorAll("th").length).toBe(2);
    expect(container.querySelector("td")?.textContent).toBe("1");
  });

  it("does not render raw HTML from the note", () => {
    const { container } = render(<MarkdownView text={"<script>window.hacked=1</script> <img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("script, img")).toBeNull();
    expect(container.textContent).toContain("<script>");
  });
});

describe("MarkdownEditor", () => {
  function Harness({ initial }: { initial: string }) {
    const [value, setValue] = useState(initial);
    return <MarkdownEditor label="Notatka" value={value} onChange={setValue} toolName="HashiCorp Vault" />;
  }

  it("shows a live preview and cleans a pasted Obsidian note, with undo", () => {
    render(<Harness initial={VAULT_NOTE} />);
    expect(screen.getByLabelText("Podgląd notatki").textContent).toContain("Key Points");
    fireEvent.click(screen.getByRole("button", { name: "Oczyść notatkę z Obsidiana" }));
    const textarea = screen.getByLabelText("Notatka") as HTMLTextAreaElement;
    expect(textarea.value).not.toContain("Licence");
    expect(screen.getByRole("status").textContent).toContain("Usunięto");
    fireEvent.click(screen.getByRole("button", { name: "Cofnij" }));
    expect((screen.getByLabelText("Notatka") as HTMLTextAreaElement).value).toContain("Licence");
  });

  it("disables cleaning when there is nothing to clean", () => {
    render(<Harness initial={"Zwykła notatka"} />);
    expect((screen.getByRole("button", { name: "Oczyść notatkę z Obsidiana" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
