import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import EntryDocuments, { type LinkedDocument } from "./entryDocuments";

const mention: LinkedDocument = {
  id: 1, relation_type: "mentioned_in", context: "film pokazuje działanie",
  recommender_document: { id: 9332, title: "Herdr w praktyce", url: "https://www.youtube.com/watch?v=Ct-mtWqV3Ro", discovery_source: "own" },
};
const catalog: LinkedDocument = {
  id: 2, relation_type: "listed_in", context: null,
  recommender_document: { id: 77, title: "Newsletter", url: null, discovery_source: null },
};

function mockFetch(status: number, body: Record<string, unknown>) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const props = { recommendationId: 17, apiUrl: "http://api", headers: { "x-api-key": "k" } };

describe("EntryDocuments", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("lists only documents linked as mentions, not catalog evidence", () => {
    render(<EntryDocuments {...props} evidences={[mention, catalog]} onChanged={vi.fn()} />);
    expect(screen.getByText(/Herdr w praktyce/)).toBeTruthy();
    expect(screen.queryByText(/Newsletter/)).toBeNull();
  });

  it("posts the typed reference with the note and reloads the radar", async () => {
    const fetchMock = mockFetch(201, { created: true });
    const onChanged = vi.fn();
    render(<EntryDocuments {...props} evidences={[]} onChanged={onChanged} />);

    fireEvent.change(screen.getByLabelText(/Dokument \(ID/), { target: { value: " https://www.youtube.com/watch?v=Ct-mtWqV3Ro " } });
    fireEvent.change(screen.getByLabelText(/Uwaga/), { target: { value: "omawia herdr" } });
    fireEvent.click(screen.getByRole("button", { name: "Powiąż" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api/tool_recommendations/17/documents");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ document: "https://www.youtube.com/watch?v=Ct-mtWqV3Ro", context: "omawia herdr" });
    expect(await screen.findByText("Dokument powiązany z wpisem.")).toBeTruthy();
  });

  it("shows the server's message when the document is unknown", async () => {
    mockFetch(404, { message: "document not found" });
    const onChanged = vi.fn();
    render(<EntryDocuments {...props} evidences={[]} onChanged={onChanged} />);

    fireEvent.change(screen.getByLabelText(/Dokument \(ID/), { target: { value: "999999" } });
    fireEvent.click(screen.getByRole("button", { name: "Powiąż" }));

    expect((await screen.findByRole("alert")).textContent).toBe("document not found");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("detaches only after a second click", async () => {
    const fetchMock = mockFetch(200, { removed: 1 });
    const onChanged = vi.fn();
    render(<EntryDocuments {...props} evidences={[mention]} onChanged={onChanged} />);

    fireEvent.click(screen.getByRole("button", { name: "Odepnij" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Na pewno odpiąć?" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("http://api/tool_recommendations/17/documents/9332");
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });
});
