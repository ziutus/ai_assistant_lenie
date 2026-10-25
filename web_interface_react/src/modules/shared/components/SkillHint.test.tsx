import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SkillHint from "./SkillHint";

describe("SkillHint", () => {
  it("shows the copyable command after opening the tip", () => {
    render(<SkillHint skill="/lenie-obsidian-note" command="/lenie-obsidian-note 42">Opis</SkillHint>);
    expect(screen.queryByText("/lenie-obsidian-note 42")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Skill /lenie-obsidian-note" }));
    expect(screen.getByText("/lenie-obsidian-note 42")).toBeTruthy();
    expect(screen.getByText("Opis")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Kopiuj komendę" })).toBeTruthy();
  });
});
