import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SkillCommand from "./SkillCommand";

describe("SkillCommand", () => {
  it("prints the ready command with the document id and copies it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<SkillCommand command="/lenie-youtube-outline 11172">Skill zapisze spis po Twojej akceptacji.</SkillCommand>);
    expect(screen.getByText("Skorzystaj ze skilla:")).toBeTruthy();
    expect(screen.getByText("/lenie-youtube-outline 11172")).toBeTruthy();
    expect(screen.getByText("Skill zapisze spis po Twojej akceptacji.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Kopiuj" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Skopiowano" })).toBeTruthy());
    expect(writeText).toHaveBeenCalledWith("/lenie-youtube-outline 11172");
  });
});
