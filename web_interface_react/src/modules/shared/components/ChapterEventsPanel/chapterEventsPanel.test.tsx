import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import ChapterEventsPanel from "./chapterEventsPanel";

vi.mock("axios");
const mocked = vi.mocked(axios, true);

afterEach(() => { cleanup(); vi.resetAllMocks(); });

const proposal = {
  date_text: "1 września 1939", event_date: "1939-09-01", event_date_end: null,
  description: "Atak na Polskę", anchor_quote: "1 września 1939 roku",
};

it("loads saved proposals of the chapter when opened", async () => {
  mocked.get.mockResolvedValue({ data: { events: [proposal] } });
  render(<ChapterEventsPanel apiUrl="http://api" apiKey="k" docId={5} position={2} />);

  fireEvent.click(screen.getByRole("button", { name: /Zdarzenia rozdziału/ }));

  expect(await screen.findByText(/Atak na Polskę/)).toBeTruthy();
  expect(mocked.get).toHaveBeenCalledWith(
    "http://api/document/5/events", expect.objectContaining({ params: { chapter_position: 2 } }),
  );
});

it("detects events for this chapter only and lists the result", async () => {
  mocked.get.mockResolvedValue({ data: { events: [] } });
  mocked.post.mockResolvedValue({
    data: { events: [proposal], model: "m1", rejected_without_quote: 1, rejected_without_date: 0 },
  });
  render(<ChapterEventsPanel apiUrl="http://api" apiKey="k" docId={5} position={2} />);

  fireEvent.click(screen.getByRole("button", { name: /Zdarzenia rozdziału/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Wykryj zdarzenia/ }));

  await waitFor(() => expect(screen.getByText(/Atak na Polskę/)).toBeTruthy());
  expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/2/detect_events");
  expect(screen.getByRole("status").textContent).toContain("1 zdarzeń");
});
