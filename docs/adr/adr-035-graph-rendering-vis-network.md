# ADR-035: Graph rendering in the web UI — stay with vis-network, Pele/Mermaid deferred

**Date:** 2026-11-08
**Status:** Accepted
**Decision makers:** Ziutus

## Context

The reader page `/read/:id` shows a relationship graph (documents, publishers, information sources, cited
publications, organizations) built by `web_interface_react/src/modules/shared/components/RelationshipGraph/relationshipGraph.tsx`.
It uses **vis-network** (`vis-network/standalone`, `^10.1.2`): the reader can drag nodes, zoom, hover for a tooltip
and click a node to open its details panel or its `/read/:id` page.

The question came up whether to render such graphs from Mermaid text instead, using
[Pele](https://pele.run/) (an MIT-licensed Mermaid renderer from the Obsidian team: Mermaid text → themeable SVG,
very fast, no DOM measuring). Neither Mermaid nor Pele is a dependency of the repo today; Mermaid only appears in
Markdown diagrams in `docs/`, rendered by GitHub/Obsidian.

## Options

1. **Stay with vis-network (chosen).** Interactive: drag, zoom, physics layout, per-node events, a details panel.
   Already in use, already tested in the reader.
2. **Pele (Mermaid → SVG).** Static picture. Colors and fonts follow CSS variables (light/dark theme for free),
   small and fast. But: its own layout (nodes and edges differ from Mermaid.js and from GitHub's rendering),
   `click` callbacks that run JavaScript are ignored (links work), no dragging, no hover details, and the project is
   young.
3. **mermaid.js.** The reference implementation, but heavy, measures the DOM, and has the same static limits as
   option 2.

## Decision

Keep **vis-network** for every graph the user explores in the UI. Do not add Mermaid or Pele now.

This is "not now", not "never". Pele is the candidate to reach for when a **static, read-only diagram** is wanted
(for example a small flow rendered from text inside a document or a note, or an exported/printed picture) —
there its theme-by-CSS-variables and speed beat vis-network. Revisit when:

- a graph is generated as Mermaid text by an LLM or a skill and shown as-is (no interaction needed);
- vis-network's physics layout becomes too slow or too noisy for a bigger graph than the reader shows today;
- the reader needs a themed (dark mode) diagram that vis-network cannot style cleanly.

## Consequences

- No new frontend dependency; the single graph library stays documented in
  [web_interface_react/CLAUDE.md](../../web_interface_react/CLAUDE.md) ("Graphs").
- A new interactive graph should reuse the vis-network setup in `RelationshipGraph` rather than introducing a
  second library.
- If Pele is adopted later, record it in a follow-up ADR and check first: license (MIT at the time of writing),
  bundle size, link handling (`click` JS is ignored), and that node layout differences are acceptable.
