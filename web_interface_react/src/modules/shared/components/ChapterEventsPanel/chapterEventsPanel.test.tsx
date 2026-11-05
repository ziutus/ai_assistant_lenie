import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import { MemoryRouter } from "react-router-dom";
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

  fireEvent.click(screen.getByRole("button", { name: /Wydarzenia z datą w rozdziale/ }));

  expect(await screen.findByText(/Atak na Polskę/)).toBeTruthy();
  expect(mocked.get).toHaveBeenCalledWith(
    "http://api/document/5/events", expect.objectContaining({ params: { chapter_position: 2 } }),
  );
});

it("lists registry events that cite the chapter even without a timeline proposal", async () => {
  mocked.get.mockResolvedValue({
    data: {
      events: [],
      registry_sources: [{
        id: 36, stance: "supports", anchor_quote: "wybrano przewodniczącego Knesetu",
        event: { id: 57, title: "Rozstrzygnięcie władzy w Izraelu", status: "proposed", event_date: "2026-11-01" },
      }],
    },
  });
  render(
    <MemoryRouter>
      <ChapterEventsPanel apiUrl="http://api" apiKey="k" docId={11234} position={2} />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByRole("button", { name: /Wydarzenia z datą w rozdziale/ }));

  const link = await screen.findByRole("link", { name: /#57 Rozstrzygnięcie władzy w Izraelu/ });
  expect(link.getAttribute("href")).toBe("/world-events?q=Rozstrzygni%C4%99cie%20w%C5%82adzy%20w%20Izraelu");
  expect(screen.getByText(/propozycja/)).toBeTruthy();
  expect(screen.getByText(/wybrano przewodniczącego Knesetu/)).toBeTruthy();
  expect(screen.queryByText(/Brak zapisanych propozycji/)).toBeNull();
  expect(screen.getByRole("button", { name: /Wydarzenia z datą w rozdziale \(1\)/ })).toBeTruthy();
});

it("detects events for this chapter only and lists the result", async () => {
  mocked.get.mockResolvedValue({ data: { events: [] } });
  mocked.post.mockResolvedValue({
    data: { events: [proposal], model: "m1", rejected_without_quote: 1, rejected_without_date: 0 },
  });
  render(<ChapterEventsPanel apiUrl="http://api" apiKey="k" docId={5} position={2} />);

  fireEvent.click(screen.getByRole("button", { name: /Wydarzenia z datą w rozdziale/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Wykryj wydarzenia/ }));

  await waitFor(() => expect(screen.getByText(/Atak na Polskę/)).toBeTruthy());
  expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/2/detect_events");
  expect(screen.getByRole("status").textContent).toContain("1 wydarzeń");
});

const withId = { ...proposal, id: 77, world_events: [] };

const renderOpen = async () => {
  render(
    <MemoryRouter>
      <ChapterEventsPanel apiUrl="http://api" apiKey="k" docId={5} position={2} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: /Wydarzenia z datą w rozdziale/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Do rejestru wydarzeń/ }));
};

const mockGets = (candidates: unknown[]) => {
  mocked.get.mockImplementation(async (url: string) => {
    if (url.endsWith("/events")) return { data: { events: [withId] } };
    if (url.endsWith("/geo_event_kinds")) {
      return { data: { kinds: [{ code: "other", label: "inne" }, { code: "market", label: "rynek" }] } };
    }
    if (url.endsWith("/world_events/candidates")) return { data: { candidates } };
    return { data: {} };
  });
};

it("promotes a proposal under a corrected title and marks it as registered", async () => {
  mockGets([]);
  mocked.post.mockResolvedValue({ data: { created: true, event: { id: 9, title: "Nord Stream 2 wybuchł" } } });
  await renderOpen();

  const input = await screen.findByLabelText(/Tytuł wydarzenia/);
  fireEvent.change(input, { target: { value: "Nord Stream 2 wybuchł" } });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj do rejestru" }));

  await waitFor(() => expect(screen.getByText(/W rejestrze wydarzeń/)).toBeTruthy());
  expect(mocked.post).toHaveBeenCalledWith(
    "http://api/document_events/77/to_world_event",
    { title: "Nord Stream 2 wybuchł", kind: "other" },
    expect.anything(),
  );
});

it("attaches the proposal as a source of an existing event the reviewer confirms", async () => {
  mockGets([{ reason: "alias", score: 1, event: { id: 4, title: "Eksplozja Nord Stream", event_date: "2022-09-26" } }]);
  mocked.post.mockResolvedValue({ data: { created: false, event: { id: 4, title: "Eksplozja Nord Stream" } } });
  await renderOpen();

  fireEvent.click(await screen.findByRole("button", { name: /Sprawdź, czy już jest/ }));
  fireEvent.click(await screen.findByLabelText(/Tak, dodaj jako źródło: #4/));
  fireEvent.click(screen.getByRole("button", { name: "Dodaj jako źródło" }));

  await waitFor(() => expect(mocked.post).toHaveBeenCalled());
  expect(mocked.post.mock.calls[0][1]).toEqual({ event_id: 4 });
});
