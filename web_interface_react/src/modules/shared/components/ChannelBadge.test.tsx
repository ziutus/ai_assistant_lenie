import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import ChannelBadge from "./ChannelBadge";

afterEach(cleanup);

it("shows the channel and links to its glossary", () => {
  render(<MemoryRouter><ChannelBadge channel=" Na Wschód od Bliskiego Wschodu " /></MemoryRouter>);
  const link = screen.getByRole("link", { name: "Kanał: Na Wschód od Bliskiego Wschodu" });
  expect(link.textContent).toContain("Na Wschód od Bliskiego Wschodu");
  expect(link.getAttribute("href")).toBe("/ner-glossary?author=Na%20Wsch%C3%B3d%20od%20Bliskiego%20Wschodu");
});

it.each([null, undefined, "", "   "])("renders nothing for %p", (channel) => {
  const { container } = render(<MemoryRouter><ChannelBadge channel={channel} /></MemoryRouter>);
  expect(container.textContent).toBe("");
});
