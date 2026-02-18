# Story 5.2: Remove Dead Frontend Monitoring Code

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to remove the unused `aws-rum-web` package, Cognito Identity Pool references, and CloudWatch RUM initialization from the React frontend,
so that the frontend codebase is clean, the bundle size is reduced, and no dead monitoring code remains.

## Acceptance Criteria

1. **Given** the React frontend in `web_interface_react/` contains unused monitoring code
   **When** developer removes the dead code
   **Then** the `aws-rum-web` package is removed from `package.json` (FR19)
   **And** the `bootstrapRum()` function is removed from `authorizationContext.js` (FR20)
   **And** the Cognito Identity Pool ID reference (`us-east-1:69944c41-8591-41a0-9037-8fc91b005c17`) is removed from `authorizationContext.js` (FR20)
   **And** all CloudWatch RUM initialization code is removed from `authorizationContext.js` (FR21)
   **And** any related imports (`import { AwsRum } from 'aws-rum-web'`) are removed
   **And** all `awsRum?.recordEvent(...)` calls in `list.jsx` are removed
   **And** the `awsRum` property is removed from `AuthorizationContext` default value and Provider value
   **And** the `awsRum` state (`useState`) and `useEffect` initialization are removed from `AuthorizationProvider`
   **And** the frontend application builds successfully without errors (`npm run build`)
   **And** the frontend application runs correctly without the removed monitoring features
   **And** no references to `aws-rum-web`, `AwsRum`, `bootstrapRum`, or `awsRum` remain in the codebase

## Tasks / Subtasks

- [x] Task 1: Remove `aws-rum-web` from package.json (AC: #1)
  - [x] 1.1: Delete `"aws-rum-web": "^1.19.0"` from `dependencies` in `web_interface_react/package.json` (line 19)
  - [x] 1.2: Run `npm install` or `yarn install` in `web_interface_react/` to update `package-lock.json` / `yarn.lock`

- [x] Task 2: Clean up `authorizationContext.js` (AC: #1)
  - [x] 2.1: Remove `import { AwsRum } from 'aws-rum-web';` (line 4)
  - [x] 2.2: Remove entire `bootstrapRum()` function (lines 8-39) — includes Cognito Identity Pool ID, CloudWatch RUM config, and AwsRum instantiation
  - [x] 2.3: Remove `awsRum: "",` from `createContext` default value (line 52)
  - [x] 2.4: Remove `const [awsRum, setAwsRum] = React.useState();` (line 73)
  - [x] 2.5: Remove the entire `useEffect` block that calls `bootstrapRum()` (lines 67-71)
  - [x] 2.6: Remove `awsRum,` from the Provider `value` object (line 100)
  - [x] 2.7: Clean up any resulting empty lines or formatting issues

- [x] Task 3: Clean up `list.jsx` (AC: #1)
  - [x] 3.1: Remove `const { awsRum } = React.useContext(AuthorizationContext);` (line 23)
  - [x] 3.2: Remove `awsRum?.recordEvent('listDocuments', {...})` in `handleTypeChange` (lines 30-33)
  - [x] 3.3: Remove `awsRum?.recordEvent('listDocuments', {...})` in `handleDocumentStateChange` (lines 39-42)
  - [x] 3.4: Remove `awsRum?.recordEvent('DeleteDocuments', {...})` in `handleDocumentDeleteOnThisPage` (lines 48-50)

- [x] Task 4: Verify build and codebase (AC: #1)
  - [x] 4.1: Run `npm run build` (or `yarn build`) in `web_interface_react/` — must succeed with zero errors
  - [x] 4.2: Run codebase-wide search for `aws-rum-web`, `AwsRum`, `bootstrapRum`, `awsRum` — must return zero matches in source code
  - [ ] 4.3: Verify the frontend loads correctly in browser (manual check)

## Dev Notes

### Scope of Changes — 3 Files Only

This is a straightforward code removal story. All changes are deletions — no new code is written.

| File | Change |
|------|--------|
| `web_interface_react/package.json` | Remove `aws-rum-web` dependency (line 19) |
| `web_interface_react/src/modules/shared/context/authorizationContext.js` | Remove import, `bootstrapRum()` function, `awsRum` state/effect/context |
| `web_interface_react/src/modules/shared/pages/list.jsx` | Remove `awsRum` context destructuring and 3 `recordEvent` calls |

### CRITICAL: list.jsx Has awsRum Usage (Not in Epics!)

The epics file mentions only `authorizationContext.js` for FR19-FR21, but **`list.jsx` also consumes `awsRum`** from context to record custom events:
- `awsRum?.recordEvent('listDocuments', ...)` — on type filter change
- `awsRum?.recordEvent('listDocuments', ...)` — on state filter change
- `awsRum?.recordEvent('DeleteDocuments', ...)` — on document delete

These `recordEvent` calls are telemetry-only and have NO functional impact — removing them will not change any application behavior.

### What Gets Removed

```
Removed from authorizationContext.js:
  - import { AwsRum } from 'aws-rum-web'
  - bootstrapRum() function (32 lines) including:
    - Cognito Identity Pool ID: us-east-1:69944c41-8591-41a0-9037-8fc91b005c17
    - RUM Application ID: 88632d7f-4bb8-47e0-991b-76c7d20fd2ec
    - RUM Endpoint: https://dataplane.rum.us-east-1.amazonaws.com
  - awsRum state (useState)
  - useEffect that calls bootstrapRum()
  - awsRum in context default value and Provider value

Removed from list.jsx:
  - awsRum context destructuring
  - 3x awsRum?.recordEvent() calls

Removed from package.json:
  - aws-rum-web dependency
```

### What Is NOT Changed

- No other files reference `awsRum`, `AwsRum`, or `bootstrapRum`
- No backend changes
- No infrastructure changes
- No changes to other context properties (apiUrl, apiKey, databaseStatus, etc.)
- No changes to any hooks or other components

### Architecture Compliance

- **FR19**: Remove `aws-rum-web` from `package.json` — reduces bundle size
- **FR20**: Remove Cognito Identity Pool reference and `bootstrapRum()` — eliminates dead authentication dependency
- **FR21**: Remove all CloudWatch RUM initialization code — cleans `authorizationContext.js`

### CLAUDE.md Update Required

After completing this story, `web_interface_react/CLAUDE.md` should be updated:
- Remove `aws-rum-web` from the Dependencies table
- Remove "AWS RUM: CloudWatch Real User Monitoring (disabled on localhost)" from Global State section
- This is a documentation-only change and can be done as part of the story or separately

### Build System

- **Package manager**: yarn (per Dockerfile) or npm
- **Build command**: `npm run build` or `yarn build`
- **Build tool**: Create React App (react-scripts 5.0.1)
- **No special build configuration needed** — just removing a dependency and its usage

### Project Structure Notes

- All changes are within `web_interface_react/` directory
- Alignment with project structure: authorizationContext.js is the single global state provider
- No conflicts or variances detected

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.2] — Acceptance criteria (FR19, FR20, FR21)
- [Source: _bmad-output/planning-artifacts/architecture.md#Requirements Overview] — FR19-FR21 scope definition
- [Source: web_interface_react/CLAUDE.md] — Frontend architecture, dependency list, directory structure
- [Source: web_interface_react/src/modules/shared/context/authorizationContext.js] — Full RUM code to remove
- [Source: web_interface_react/src/modules/shared/pages/list.jsx] — awsRum.recordEvent calls to remove
- [Source: web_interface_react/package.json] — aws-rum-web dependency at line 19
- [Source: _bmad-output/implementation-artifacts/5-1-remove-legacy-aws-resources.md] — Previous story context, lessons learned

### Previous Story Intelligence (5.1)

Key learnings from Story 5.1 that apply:
1. **Verify before acting** — confirm each change target exists before modifying
2. **Codebase-wide search after changes** — grep for all variations of removed identifiers
3. **Update documentation** — CLAUDE.md and README files should reflect the cleanup
4. Story 5.1 was purely AWS infrastructure — this story is purely frontend code. No AWS CLI commands needed.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Removed `aws-rum-web` dependency from package.json (37 packages removed from node_modules)
- Cleaned authorizationContext.js: removed AwsRum import, bootstrapRum() function (32 lines including Cognito Identity Pool ID, RUM config), awsRum state/useEffect/context entries
- Cleaned list.jsx: removed awsRum context destructuring and 3 recordEvent() calls
- Build succeeds with zero errors (only pre-existing eslint warnings remain)
- Codebase-wide search confirms zero remaining references to aws-rum-web, AwsRum, bootstrapRum, or awsRum
- Updated web_interface_react/CLAUDE.md: removed aws-rum-web from Dependencies table and AWS RUM from Global State section
- Task 4.3 (manual browser verification) left unchecked — requires manual testing by developer

### Change Log

- 2026-02-15: Removed all CloudWatch RUM monitoring code from React frontend (Story 5.2)
- 2026-02-15: Code review — fixed indentation in authorizationContext.js Provider value, cleaned File List (removed BMAD artifacts and non-tracked package-lock.json)

### File List

- web_interface_react/package.json (modified — removed aws-rum-web dependency)
- web_interface_react/src/modules/shared/context/authorizationContext.js (modified — removed RUM import, bootstrapRum(), awsRum state/effect/context; fixed indentation)
- web_interface_react/src/modules/shared/pages/list.jsx (modified — removed awsRum context usage and recordEvent calls)
- web_interface_react/CLAUDE.md (modified — removed aws-rum-web from docs)
