import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ToolProfileSuggest, { type ProfileSuggestion } from "./toolProfileSuggest";

const suggestion = (overrides: Partial<ProfileSuggestion> = {}): ProfileSuggestion => ({
  status: "ok", model: "openrouter/google/gemini-2.5-flash-lite", description: "Interaktywne środowisko do notatników Jupyter.",
  category: "DataScience", category_is_new: false, category_changed: true, tags: ["python", "jupyter"], confidence: "known",
  tokens: 900, cost: "0.0004", currency: "USD", ...overrides,
});

const setup = (result: ProfileSuggestion | Error, props: Partial<React.ComponentProps<typeof ToolProfileSuggest>> = {}) => {
  const handlers = {
    onSuggest: vi.fn(() => result instanceof Error ? Promise.reject(result) : Promise.resolve(result)),
    onUseDescription: vi.fn(), onUseCategory: vi.fn(), onAddTags: vi.fn(),
  };
  render(<ToolProfileSuggest description="JupyterLab computational environment." category="AI" tags={["notebooks"]} disabled={false}
    {...handlers} {...props} />);
  return handlers;
};

const ask = async () => {
  fireEvent.click(screen.getByRole("button", { name: /Podpowiedz opis, kategorię i tagi/ }));
  await waitFor(() => expect(screen.queryByText("Myślę…")).toBeNull());
};

describe("ToolProfileSuggest", () => {
  afterEach(() => cleanup());

  it("asks once and saves nothing until a button is clicked", async () => {
    const handlers = setup(suggestion());
    await ask();

    expect(handlers.onSuggest).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Interaktywne środowisko/)).toBeTruthy();
    expect(screen.getByText(/może się mylić/)).toBeTruthy();
    expect(screen.getByText(/model zna to narzędzie/)).toBeTruthy();
    expect(handlers.onUseDescription).not.toHaveBeenCalled();
    expect(handlers.onUseCategory).not.toHaveBeenCalled();
    expect(handlers.onAddTags).not.toHaveBeenCalled();
    expect(screen.getByText(/0.0004 USD/)).toBeTruthy();
  });

  it("accepts the description, the category and each tag separately", async () => {
    const handlers = setup(suggestion());
    await ask();

    fireEvent.click(screen.getByRole("button", { name: "Zastąp opis" }));
    expect(handlers.onUseDescription).toHaveBeenCalledWith("Interaktywne środowisko do notatników Jupyter.");
    expect(screen.getByText("✓ zapisano")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Użyj kategorii" }));
    expect(handlers.onUseCategory).toHaveBeenCalledWith("DataScience");

    fireEvent.click(screen.getByRole("button", { name: "+ #python" }));
    expect(handlers.onAddTags).toHaveBeenLastCalledWith(["python"]);
    expect(screen.queryByRole("button", { name: "+ #python" })).toBeNull();
    expect(screen.getByRole("button", { name: "+ #jupyter" })).toBeTruthy();
  });

  it("adds all remaining tags at once and never offers tags the entry already has", async () => {
    const handlers = setup(suggestion({ tags: ["notebooks", "python", "jupyter"] }));
    await ask();
    expect(screen.queryByRole("button", { name: "+ #notebooks" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Dodaj wszystkie" }));
    expect(handlers.onAddTags).toHaveBeenCalledWith(["python", "jupyter"]);
  });

  it("flags a new category and keeps an unchanged one quiet", async () => {
    setup(suggestion({ category: "NoteTakingApps", category_is_new: true }));
    await ask();
    expect(screen.getByText("nowa")).toBeTruthy();
    cleanup();

    setup(suggestion({ category: "AI", category_changed: false }));
    await ask();
    expect(screen.getByText(/bez zmian \(AI\)/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Użyj kategorii" })).toBeNull();
  });

  it("does not offer a description identical to the current one", async () => {
    setup(suggestion({ description: "JupyterLab computational environment." }));
    await ask();
    expect(screen.getByText("(taki sam jak Twój opis)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^(Zastąp opis|Użyj jako opisu)$/ })).toBeNull();
  });

  it("says so when the model does not know the tool, with no description to accept", async () => {
    setup(suggestion({ confidence: "unknown", description: "", tags: [], category_changed: false, category: "AI" }));
    await ask();
    expect(screen.getByText(/model nie zna tego narzędzia/)).toBeTruthy();
    expect(screen.queryByText("Opis:")).toBeNull();
    expect(screen.getByText("Brak nowych tagów do zaproponowania.")).toBeTruthy();
  });

  it("shows an error instead of an empty proposal", async () => {
    setup(suggestion({ status: "error", error_code: "unparseable_answer" }));
    await ask();
    expect(screen.getByRole("alert").textContent).toContain("unparseable_answer");
    cleanup();

    setup(new Error("HTTP 503"));
    await ask();
    expect(screen.getByRole("alert").textContent).toContain("HTTP 503");
  });

  it("closes the proposal", async () => {
    setup(suggestion());
    await ask();
    fireEvent.click(screen.getByRole("button", { name: "Zamknij" }));
    expect(screen.queryByText(/Interaktywne środowisko/)).toBeNull();
  });
});
