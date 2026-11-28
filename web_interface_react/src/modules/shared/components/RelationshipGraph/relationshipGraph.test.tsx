import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import RelationshipGraph, { relationEdgeData, visibleGraphNodes, type RelationshipGraphData } from "./relationshipGraph";
vi.mock("vis-network/standalone", () => ({ DataSet: class { constructor(public data: unknown) {} }, Network: class { on() {} destroy() {} } }));
afterEach(cleanup);
const data: RelationshipGraphData = { nodes: [{ id: "1", type: "person", label: "Ada" }, { id: "2", type: "country", label: "Polska" }, { id: "3", type: "organization", label: "Samotna" }], edges: [{ id: "e", source: "1", target: "2", type: "rola", status: "proposed" }] };
it("filters only isolated nodes and defaults based on relation edges", () => {
  expect(visibleGraphNodes(data, false).map(n => n.id)).toEqual(["1", "2"]);
  expect(visibleGraphNodes(data, true)).toHaveLength(3);
  const { rerender } = render(<RelationshipGraph data={data} />);
  const checkbox = screen.getByRole("checkbox") as HTMLInputElement;
  expect(checkbox.checked).toBe(false);
  fireEvent.click(checkbox); expect(checkbox.checked).toBe(true);
  rerender(<RelationshipGraph data={{ ...data, edges: [] }} />);
  expect(checkbox.checked).toBe(true);
  expect(screen.getByText("Państwo")).toBeTruthy();
});
it("styles proposals/outside-period edges and renders evidence as literal text", () => {
  const edge = relationEdgeData({ ...data.edges[0], outside_period: true, evidence_excerpt: '<img src=x onerror="alert(1)">' });
  expect(edge.dashes).toBe(true); expect(edge.color).toEqual({ color: "#b0b8c3", highlight: "#94a3b8" });
  expect(edge.label).toBe("rola");
  const title = edge.title as HTMLElement;
  expect(title.textContent).toContain("(propozycja)"); expect(title.textContent).toContain("poza okresem publikacji");
  expect(title.querySelector("img")).toBeNull(); expect(title.textContent).toContain("<img");
  expect(relationEdgeData({ ...data.edges[0], status: "confirmed" }).dashes).toBe(false);
});
