# ADR-022: Browser timezone now; stored user timezone with user profiles

**Date:** 2026-08-13  
**Status:** Accepted  
**Decision makers:** Ziutus

## Context

The external-services status page reports the time of the most recent success
or failure. Database timestamps are stored as UTC. Showing an unlabelled value
such as `2026-08-13 08:02:27` makes it unclear whether it is UTC or the
reader's local time.

Lenie currently has no user-profile model or user authentication suitable for
persisting individual preferences.

## Decision

Until user profiles exist:

- Backend APIs serialize instants explicitly as UTC ISO 8601 values, e.g.
  `2026-08-13T08:02:27Z`.
- The web UI formats those values in the browser's local IANA timezone and
  shows the timezone abbreviation/name where space permits.

Introduce a `users`/user-profile model with a validated IANA timezone (for
example `Europe/Warsaw`) when Lenie introduces either of these capabilities:

1. multi-user authentication and authorization; or
2. user-specific scheduled reports, notifications, digests, or exports whose
   displayed schedule must remain stable independently of the device/browser.

The stored profile timezone will then be the default for server-scheduled
communication and user-selected reporting. API timestamps remain UTC; clients
may render them using the profile timezone or an explicit per-view choice.

## Consequences

- A user travelling or using another device sees interactive status times in
  that device's local timezone, which is appropriate for live troubleshooting.
- There is no premature schema, migration, authentication surface, or privacy
  data to maintain for the current single-user deployment.
- Any future profile implementation must use IANA timezone identifiers, not
  fixed UTC offsets, so daylight-saving transitions work correctly.
