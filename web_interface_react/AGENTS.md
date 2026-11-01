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

## Voice of status labels (who decided)

A label that records a decision is worded by who made it. When the user decided
(a status they set, a stage they moved an item to), use the first person:
`Obserwuję`, `Porównuję`, `Testuję`, `Używam`, `Odrzuciłem`. When an LLM or the
system decided (an automatic classification, a rejected suggestion, a detected
duplicate), use the third person: `System odrzucił`, `Model zaproponował`. Do
not mix the two voices in one set of labels. Action buttons stay imperative
(`Odrzuć`, `Testuj`). Keep this in sync with `CLAUDE.md` (UX conventions).

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

## Collapsible sections

Use native `<details><summary>` through `CollapsibleSection` for collapsible sections.
Never add a separate Zwiń/Rozwiń button. After an action completes a section
(description fetched, chapter marked as noise/advertisement), start it collapsed.
Keep actions that must remain readily accessible outside the collapsible content.

## Error messages (failed requests)

A user who sees "Network Error" can do nothing, and an engineer who is told
"it said Network Error" has to reconstruct the case from server logs. Every
message for a failed request must therefore carry both a plain explanation and
the facts needed to debug it without asking the user anything.

Build it with `describeRequestError(error, operation, { startedAt?, context? })`
from `src/modules/shared/utils/requestError.ts` and show the details with
`components/RequestErrorDetails` (a native `<details>` "Szczegóły techniczne"
plus "Kopiuj szczegóły"). Do not hand-format `error.message`.

- **Summary (always visible):** `<what the user was doing, as a failure>: <why>`,
  in Polish, e.g. `Nie udało się wykryć encji: brak odpowiedzi serwera — …`.
  Start from the operation, not from the exception. When the server sent a
  `message`, show it verbatim (backend messages are already Polish and meant for
  the user). Never show raw English client text such as `Request failed with
  status code 500` or `Network Error` as the only reason.
- **Say what to do next.** No response (`ERR_NETWORK`): the request did not reach
  the backend or the answer was blocked — check the connection and the API
  address in `/connect`, refresh, retry. Timeout (`ECONNABORTED`): the operation
  may still have run — reload the data before retrying. HTTP 4xx: what is wrong
  with the input. HTTP 5xx: the server failed, retrying later may help.
- **Details (collapsed, copyable):** operation, identifying context (document id,
  entity id — pass `context: { Dokument: docId }`), method and full target URL,
  the page it came from (`origin + pathname`), local time of the failure with the
  UTC offset, request duration (pass `startedAt: Date.now()` taken before the
  call), HTTP status and server message or "brak", client error code. The
  duration is diagnostic: a failure after 50 ms never left the browser (CORS,
  wrong host, stale tab), one after the full timeout is a slow or hung backend.
- **Never include** the API key, request headers, request bodies or document
  text — the details are meant to be pasted into chats and bug reports.
- **Keep the context where the user is looking:** show the message next to the
  control that failed (or in the existing page-level banner, see `/feed-review`),
  not in `alert()` or the console only. Log the full error with `console.error`
  as well.
- **Clear stale details** when the next plain message replaces an error
  (`EntitiesPanel` does this in its `setMessage` wrapper).
- A new handler for a request that can fail uses this helper from the start; when
  you touch an old `catch` that formats `error.message` by hand, convert it.
  Tests: assert the summary and that the details contain the target URL.
