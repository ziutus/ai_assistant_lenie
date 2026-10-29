import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { FeedSummary, SUMMARY_COLLAPSE_AT } from "./feedReview";

afterEach(cleanup);

it("shows a short summary in full without a toggle", () => {
  render(<FeedSummary text="Krótkie streszczenie." />);
  expect(screen.getByText("Krótkie streszczenie.")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});

it("collapses a long summary and expands it on demand", () => {
  const text = "słowo ".repeat(SUMMARY_COLLAPSE_AT);
  render(<FeedSummary text={text} />);
  const toggle = screen.getByRole("button", { name: `Pokaż całe streszczenie (${text.length} znaków)` });
  expect(screen.getByText(/…$/)).toBeTruthy();
  fireEvent.click(toggle);
  expect(screen.getByText(text.trim())).toBeTruthy();
  expect(screen.getByRole("button", { name: "Zwiń streszczenie" })).toBeTruthy();
});
