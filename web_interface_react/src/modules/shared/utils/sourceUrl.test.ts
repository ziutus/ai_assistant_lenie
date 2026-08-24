import { beforeEach, describe, expect, it } from "vitest";
import { saveObsidianVaultName } from "../services/storage";
import { isOpenableSourceUrl, toOpenableSourceUrl } from "./sourceUrl";

describe("toOpenableSourceUrl", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("passes through an ordinary http(s) URL unchanged", () => {
    expect(toOpenableSourceUrl("https://example.com/article")).toBe("https://example.com/article");
  });

  it("converts a gmail:// synthetic URL to an openable Gmail link", () => {
    expect(toOpenableSourceUrl("gmail://abc123")).toBe("https://mail.google.com/mail/u/0/#all/abc123");
  });

  it("converts an obsidian:// synthetic note URL into a real obsidian://open?... link", () => {
    // Regression: clicking the raw obsidian://<relative_path> URL stored as
    // documents.url (see _note_url() in obsidian_reimport_service.py) opened
    // Obsidian's URI handler with "02-wiedza" as the action name, which
    // Obsidian doesn't recognize ("nieznana akcja") -- only
    // obsidian://open?file=... is a valid Obsidian URI.
    const result = toOpenableSourceUrl("obsidian://02-wiedza/Informatyka/Linux/Linux i BIOS.md");
    expect(result).toBe("obsidian://open?file=02-wiedza%2FInformatyka%2FLinux%2FLinux%20i%20BIOS");
  });

  it("handles an already percent-encoded obsidian:// URL (e.g. copied from a rendered <a href>)", () => {
    const result = toOpenableSourceUrl("obsidian://02-wiedza/Informatyka/Linux/Linux%20i%20BIOS.md");
    expect(result).toBe("obsidian://open?file=02-wiedza%2FInformatyka%2FLinux%2FLinux%20i%20BIOS");
  });

  it("includes the device-local vault name when one is configured", () => {
    saveObsidianVaultName("personal");
    const result = toOpenableSourceUrl("obsidian://02-wiedza/k8s.md");
    expect(result).toBe("obsidian://open?vault=personal&file=02-wiedza%2Fk8s");
  });

  it("does not touch a real obsidian://open?... URL", () => {
    const url = "obsidian://open?vault=personal&file=02-wiedza%2Fk8s";
    expect(toOpenableSourceUrl(url)).toBe(url);
  });
});

describe("isOpenableSourceUrl", () => {
  it("rejects whatsapp:// synthetic dedup identities (no real destination to open)", () => {
    expect(isOpenableSourceUrl("whatsapp://tuwima-gardens/czat-ogolny/osoba/48_789_341_361")).toBe(false);
  });

  it("accepts ordinary http(s) URLs", () => {
    expect(isOpenableSourceUrl("https://example.com/article")).toBe(true);
  });

  it("accepts gmail:// and obsidian:// URLs, which have real openable targets", () => {
    expect(isOpenableSourceUrl("gmail://abc123")).toBe(true);
    expect(isOpenableSourceUrl("obsidian://02-wiedza/k8s.md")).toBe(true);
  });
});
