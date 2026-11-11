import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import ChapterSourcesPanel, { sourcesOfChapter, type DocumentSourceEntry } from "./chapterSourcesPanel";

vi.mock("axios");
const mocked = vi.mocked(axios, true);

afterEach(() => { cleanup(); vi.resetAllMocks(); });

const CHAPTER = "W 2015 roku opublikowano badanie Sherry Towers i współautorów o zarażaniu przemocą. Dalej coś innego.";

const towers: DocumentSourceEntry = {
  id: 7, source_id: 3, canonical_name: "Towers i in. (2015)", source_type: "study", organization_id: null,
  role: "cited", evidence_excerpt: "badanie Sherry Towers i współautorów", review_status: "needs_review",
  extraction_method: "timeline_publication",
};

const render_ = (entries: DocumentSourceEntry[], chapterText = CHAPTER) => {
  mocked.get.mockResolvedValue({ data: { entries } });
  return render(<ChapterSourcesPanel apiUrl="http://api" apiKey="k" docId={11251} chapterText={chapterText} />);
};

it("shows a publication source of the chapter with its quote and the review badge", async () => {
  render_([towers]);

  expect(await screen.findByText("Towers i in. (2015)")).toBeTruthy();
  expect(screen.getByText(/Źródła informacji \(1\):/)).toBeTruthy();
  expect(screen.getByText("do potwierdzenia")).toBeTruthy();
  expect(screen.getByText(/„badanie Sherry Towers i współautorów”/)).toBeTruthy();
  expect(mocked.get).toHaveBeenCalledWith("http://api/document/11251/information_sources", expect.anything());
});

it("leaves out organizations (they are chips), the publisher and sources quoted in another chapter", () => {
  const entries = [
    towers,
    { ...towers, id: 8, canonical_name: "WHO", organization_id: 4 },
    { ...towers, id: 9, canonical_name: "bankier.pl", role: "publisher" },
    { ...towers, id: 10, canonical_name: "Gdzie indziej", evidence_excerpt: "zupełnie inny cytat z innego rozdziału" },
    { ...towers, id: 11, canonical_name: "Bez cytatu", evidence_excerpt: null },
  ];

  expect(sourcesOfChapter(entries, CHAPTER).map((entry) => entry.id)).toEqual([7]);
});

it("matches a quote whatever the quotation marks, dashes and spacing", () => {
  const entry = { ...towers, evidence_excerpt: "„badanie  Sherry Towers” – i współautorów" };

  expect(sourcesOfChapter([entry], CHAPTER)).toHaveLength(1);
});

it("draws nothing when the chapter has no such source", async () => {
  const { container } = render_([{ ...towers, evidence_excerpt: "nie ma tego w rozdziale" }]);

  await waitFor(() => expect(mocked.get).toHaveBeenCalled());
  expect(container.textContent).toBe("");
});

it("approves a source", async () => {
  render_([towers]);
  mocked.patch.mockResolvedValue({ data: { status: "success" } });

  fireEvent.click(await screen.findByRole("button", { name: /Zatwierdź/ }));

  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Zatwierdzono"));
  expect(mocked.patch).toHaveBeenCalledWith(
    "http://api/document/11251/information_sources/7", { review_status: "approved" }, expect.anything(),
  );
});

it("rejects a source and reloads the list", async () => {
  render_([towers]);
  mocked.patch.mockResolvedValue({ data: { status: "success" } });

  fireEvent.click(await screen.findByRole("button", { name: /Odrzuć/ }));
  mocked.get.mockResolvedValue({ data: { entries: [] } });

  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Odrzucono"));
  expect(mocked.patch.mock.calls[0][1]).toEqual({ review_status: "rejected" });
  await waitFor(() => expect(screen.queryByText("Towers i in. (2015)")).toBeNull());
});

it("renames and retypes a source", async () => {
  render_([towers]);
  mocked.patch.mockResolvedValue({ data: { status: "success" } });

  fireEvent.click(await screen.findByRole("button", { name: /Edytuj/ }));
  fireEvent.change(screen.getByLabelText(/Nazwa źródła/), { target: { value: "Towers, Gould i in. (2015)" } });
  fireEvent.change(screen.getByLabelText(/Rodzaj źródła/), { target: { value: "report" } });
  fireEvent.change(screen.getByLabelText(/Rola w dokumencie/), { target: { value: "data_source" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

  await waitFor(() => expect(mocked.patch).toHaveBeenCalled());
  expect(mocked.patch).toHaveBeenCalledWith(
    "http://api/document/11251/information_sources/7",
    { name: "Towers, Gould i in. (2015)", source_type: "report", role: "data_source" },
    expect.anything(),
  );
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Zapisano źródło"));
});

it("shows the server's reason when saving fails", async () => {
  render_([towers]);
  mocked.patch.mockRejectedValue(Object.assign(new Error("Request failed"), {
    isAxiosError: true, response: { status: 409, data: { message: "Ten dokument ma już takie źródło w tej roli" } },
  }));

  fireEvent.click(await screen.findByRole("button", { name: /Zatwierdź/ }));

  expect(await screen.findByRole("alert")).toBeTruthy();
});
