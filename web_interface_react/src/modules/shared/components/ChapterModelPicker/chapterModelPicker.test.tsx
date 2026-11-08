import { act, fireEvent, render, screen } from "@testing-library/react";
import axios from "axios";
import { afterEach, expect, it, vi } from "vitest";
import ChapterModelPicker, { useChapterModel } from "./chapterModelPicker";

vi.mock("axios");

const Harness = () => {
  const state = useChapterModel("http://api", "key");
  return <ChapterModelPicker state={state} />;
};

afterEach(() => vi.resetAllMocks());

it("lets the reviewer retry after the model list failed to load", async () => {
  vi.mocked(axios.get)
    .mockRejectedValueOnce({ message: "Network Error", request: {}, config: { method: "get", url: "/chapter_analysis/model" } })
    .mockResolvedValueOnce({ data: { models: [{ id: "bielik", label: "Bielik" }], default_model: "bielik", saved: false } });
  const { container } = render(<Harness />);
  const details = container.querySelector("details") as HTMLDetailsElement;
  await act(async () => { details.open = true; await new Promise((resolve) => setTimeout(resolve, 20)); });
  const retry = await screen.findByRole("button", { name: "Spróbuj ponownie" });
  await act(async () => { fireEvent.click(retry); });
  expect(axios.get).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("button", { name: "Spróbuj ponownie" })).toBeNull();
});
