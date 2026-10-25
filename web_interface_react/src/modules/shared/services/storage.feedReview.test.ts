import { afterEach, expect, it } from "vitest";
import { loadFeedReviewFilters, saveFeedReviewFilters } from "./storage";

afterEach(() => localStorage.clear());

it("persists the discussion view", () => {
  saveFeedReviewFilters({ view: "discuss", feedSourceId: "2", mode: "all" });
  expect(loadFeedReviewFilters()).toEqual({ view: "discuss", feedSourceId: "2", mode: "all" });
});

it("falls back to new for unknown stored views", () => {
  localStorage.setItem("lenie_feedReviewFilters", JSON.stringify({ view: "invalid" }));
  expect(loadFeedReviewFilters().view).toBe("new");
});
