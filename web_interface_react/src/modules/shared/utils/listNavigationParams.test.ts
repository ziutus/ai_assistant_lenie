import { describe, expect, it } from "vitest";
import { listNavigationParams } from "./listNavigationParams";

describe("reader list filters", () => {
  it.each(["link", "link,webpage"])("preserves type %s and maps status CSV", type => {
    const params = listNavigationParams(`type=${type}&status=URL_ADDED,NEED_MANUAL_REVIEW&q=test&obsidian=missing`, "42")!;
    expect(params.get("type")).toBe(type);
    expect(params.get("processing_status")).toBe("URL_ADDED,NEED_MANUAL_REVIEW");
    expect(params.get("document_id")).toBe("42");
    expect(params.get("q")).toBe("test");
    expect(params.get("only_missing_obsidian_notes")).toBe("true");
  });
  it.each(["", "type=", "status="])("skips navigation for empty selection %s", context => {
    expect(listNavigationParams(context, "42")).toBeNull();
  });
  it("keeps unrestricted and other list filters", () => {
    const params = listNavigationParams("type=ALL&status=ALL&obsidian=has&topic_filter=1&topic_group_ids=1,2&sort=priority", "42")!;
    expect(params.get("processing_status")).toBe("ALL");
    expect(params.get("only_has_obsidian_notes")).toBe("true");
    expect(params.get("topic_group_ids")).toBe("1,2");
    expect(params.get("sort")).toBe("priority");
  });
});
