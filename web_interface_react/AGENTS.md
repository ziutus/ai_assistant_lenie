# AGENTS.md — web_interface_react

Rules for agents (Codex, Claude Code) editing the React frontend. Details and
the rest of the UX conventions live in [CLAUDE.md](CLAUDE.md) ("UX conventions");
this file states the rules that must not be missed.

## Selection controls (choosing values from a list)

Pick the control by how many values the user can choose:

- **One value from a few options** → native `<select>` (or radios for 2-3
  options). Do not build a custom dropdown for this.
- **Several values from one category** (filters: topics, groups, document
  types, statuses, ...) → the shared
  `src/modules/shared/components/MultiSelectFilter/MultiSelectFilter.tsx`.
  Never copy its markup or its outside-click handling into a page; if it lacks
  something, extend the component.
- **Independent yes/no switches and form fields** → plain checkboxes/inputs.

`MultiSelectFilter` requirements (already built in, keep them when changing it):

- Trigger text is `Wszystkie [kategorie]` or `<Etykieta>: wybrano N`.
- Menu actions: `Zaznacz wszystkie`, `Odznacz wszystkie`, `Odwróć wybór`.
- Every option, including the empty-value option, has a `tylko` button that
  selects that value alone (UI strings are Polish — never the English "only").
- A meaningful empty value (for example `(bez tematów)`, `(bez grupy)`) is a
  separate `emptyOption`, not a normal item.
- Use `variant="select"` when the filter sits next to native `<select>`s.
- Pass `onTelemetry` where the page records browse telemetry; every action,
  including `tylko`, must trigger it.

State rules for multi-value filters:

- The owning page keeps the state and persists the **complete** filter in the
  URL, so the filtered view is shareable. Single-value legacy URLs must keep
  working.
- A backend endpoint that accepts several values takes a comma-separated list;
  a missing parameter or `ALL` means "no filter". Selecting nothing shows an
  empty result with a Polish message and does not call the API.
- Inclusion/exclusion filters (for example contact interests) may keep local
  controls, but still offer `tylko`.

When the same selection pattern is needed in a second view, extract or reuse a
shared component instead of duplicating it.

## Entity chips (NER: persons, organizations, places, events, products)

Every entity chip, whatever its type, is drawn by `EntityChips` in
`src/modules/shared/components/EntitiesPanel/entitiesPanel.tsx` and gets its
actions from that file's `MenuEntry` dropdown (`personMenuActions`,
`organizationMenuActions`, `placeMenuActions`, `eventMenuActions`,
`productMenuActions`). A page never draws its own chip row with inline buttons
(`×`, `⇄`, icon buttons) — that is how the product chip ended up different from
the others. A new entity type means: chip menu in `EntitiesPanel` first, page
code second.

- Page-owned dialogs (an event's description, the product merge form) are
  opened from the menu through a callback prop (`onDescribeEvent`,
  `onMergeProducts`, like `onShowInText`), not by a second set of buttons.
- Every type's menu has the entries listed in the matrix in
  [CLAUDE.md](CLAUDE.md) ("Entity chip menus"): copy name, highlight in text,
  change type to every other type, delete. When you add an entity type or a
  retype endpoint, update that matrix and the tests in `entitiesPanel.test.tsx`
  (they assert the exact menu lists).
