import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import AddressMapMenu, { buildMapLinks } from "./AddressMapMenu";

afterEach(cleanup);

const plain = { formatted_address: "Olsztyńska 16, Łódź, Polska", latitude: null, longitude: null };
const geocoded = { ...plain, latitude: 51.75, longitude: 19.45 };

it("falls back to the text query when the address has no coordinates", () => {
  const links = buildMapLinks(plain);
  const q = encodeURIComponent(plain.formatted_address);
  expect(links.find(l => l.label.startsWith("Google Maps — trasa"))?.href).toContain(`destination=${q}`);
  expect(links.find(l => l.label.startsWith("OpenStreetMap — pokaż"))?.href).toContain(`search?query=${q}`);
  expect(links.some(l => l.label.includes("OpenStreetMap — trasa"))).toBe(false);
});

it("prefers coordinates and adds an OSM route when geocoded", () => {
  const links = buildMapLinks(geocoded);
  expect(links.find(l => l.label.startsWith("Google Maps — trasa"))?.href).toContain("destination=51.75,19.45");
  expect(links.find(l => l.label.includes("OpenStreetMap — trasa"))?.href).toContain("route=%3B51.75%2C19.45");
});

it("offers geocoding instead of the inline map when coordinates are missing", () => {
  const onGeocode = vi.fn();
  render(<AddressMapMenu address={plain} inlineOpen={false} onToggleInline={vi.fn()} onGeocode={onGeocode} />);
  fireEvent.click(screen.getByText("📍 Geokoduj i pokaż mapę poniżej"));
  expect(onGeocode).toHaveBeenCalledTimes(1);
});

it("highlights the menu item under the pointer", () => {
  render(<AddressMapMenu address={plain} inlineOpen={false} onToggleInline={vi.fn()} onGeocode={vi.fn()} />);
  const item = screen.getByText("Waze — nawiguj");
  expect(item.style.background).toBe("none");
  fireEvent.mouseEnter(item);
  expect(item.style.background).not.toBe("none");
  fireEvent.mouseLeave(item);
  expect(item.style.background).toBe("none");
});

it("toggles the inline map when coordinates exist", () => {
  const onToggle = vi.fn();
  render(<AddressMapMenu address={geocoded} inlineOpen={false} onToggleInline={onToggle} onGeocode={vi.fn()} />);
  fireEvent.click(screen.getByText("🗺 Pokaż mapę poniżej"));
  expect(onToggle).toHaveBeenCalledTimes(1);
});
