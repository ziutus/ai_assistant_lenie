# ADR-028: Google Contacts sync via People API, keyed by a per-account link table

**Date:** 2026-09-23
**Status:** Proposed — plan only; no implementation yet, deliberately deferred to a follow-up session
**Decision makers:** Ziutus

## Context

The private contact book (`contacts` table, `backend/library/contact_routes.py`)
is today populated from Google Contacts by a one-off, manually-triggered CSV
import (`backend/imports/google_contacts_import.py`): export contacts to CSV
from Google's web UI, run the script, review a log of matches/conflicts.

`Contact` already has a `google_contact_resource_name` column
(`backend/library/db/models.py:3140`), documented in its own class docstring
as "a placeholder for a future Google Contacts sync (no sync logic exists
yet)" — the intent to eventually sync properly was anticipated, but nothing
implements it, and the column has never been written to.

Two concrete problems surfaced while running a CSV import on 2026-09-23
(453-row export, `tmp/contacts_private.csv`):

1. **No stable identity to match on.** The CSV export contains no
   Google-internal contact ID (`resourceName`) — confirmed by inspecting the
   header row, no `id`/`resourceName` column exists. `google_contacts_import.py`
   therefore matches purely on normalized phone number, then normalized
   `first_name`+`last_name`. This produces false-positive conflicts
   ("telefony wskazują kilka kontaktów" / "ten sam telefon, ale różne nazwy")
   for ordinary real-world messiness that has nothing to do with actual
   ambiguity: nicknames (Baśka ↔ Barbara), a stray annotation appended to a
   name field ("Włodzimierz Bartczak (OSM)"), spelling drift between two
   Google entries for the same person, maiden vs. married name. In the
   2026-09-23 run, 13 of 453 rows needed a manual conversation to resolve;
   several of those were pre-existing duplicate `Contact` rows the phone
   number alone was enough to expose but not enough to safely auto-merge.
   The actual Google People API exposes a real `resourceName`
   (e.g. `people/c1234567890`), stable across a contact's lifetime on that
   account — matching on it instead of name/phone would eliminate this whole
   class of false conflict for anything already linked once.

2. **The user has more than one Google account.** An old personal Google
   account and a newer one tied to a sole proprietorship (JDG) both hold
   contacts, some overlapping (the same real person saved in both). Today's
   single `google_contact_resource_name` column can't represent that: it's
   `unique=True` on `Contact`, so one `Contact` row can carry at most one
   Google identifier, ever — there's no way to record "this person is also
   `people/c987654321` on the JDG account." A `resourceName` is only
   guaranteed unique *within* one Google account's contact list; two
   different accounts have no shared namespace guarantee, so treating the
   column as a single global unique key is not just insufficient, it is the
   wrong shape even before considering the multiplicity problem.

Stable-ID matching (item 1) fixes *identity resolution* on re-sync. It does
**not** fix *data quality at the source* — a typo the user made in Google
Contacts, or the same person saved twice under a maiden and a married name,
still needs either manual correction in Google Contacts itself, or Lenie's
own separate maiden-name/former-surname feature (tracked separately, not in
scope here — see the "Related work" note below).

## Decision (proposed shape — not yet implemented)

1. **Sync via Google People API (OAuth), not CSV export.**
   `backend/library/google_auth.py` already has OAuth 2.0 credential
   handling to build on. Use the API's `resourceName` as the durable match
   key going forward; CSV import remains available as a fallback/manual
   path but stops being the primary sync mechanism once this lands.

2. **Replace the single `google_contact_resource_name` column with a link
   table**, following the existing one-contact-many-rows pattern already
   used in this same model file for exactly this shape of problem
   (`ContactAddress` at `backend/library/db/models.py:3326`,
   `ContactOrganization` at `:3347` — "a contact's use of a shared address/
   organization, with its own role"):

   ```
   contact_google_links
     id              PK
     contact_id      FK -> contacts.id (ondelete CASCADE)
     google_account  identifies which Google account this came from
                      (e.g. the account's own e-mail address)
     resource_name   Google's people/cXXXXXXXXXX identifier
     created_at / updated_at
     UNIQUE (google_account, resource_name)
   ```

   This lets one `Contact` carry links to both a personal-account
   `resourceName` and a JDG-account `resourceName` for the same real person,
   and makes the uniqueness constraint match Google's actual guarantee
   (unique per account, not globally). Drop `google_contact_resource_name`
   from `Contact` entirely — it has never been populated, so no data
   migration is needed, only a column removal.

3. **Open design questions for the implementing session:**
   - Sync model: one pass per Google account with its own OAuth token
     (simpler, matches the account boundary already in the data model), or
     a single combined pass? Leaning toward per-account, run separately.
   - Conflict handling when the *same* real person's two Google accounts
     disagree on a field (e.g. different phone numbers, different notes) —
     does Lenie need a provenance indicator per field/change (similar in
     spirit to `discovery_sources` on `Document`) showing which Google
     account a given piece of data came from, so a human can judge which to
     trust?
   - Whether initial rollout requires a one-time manual linking pass over
     the ~480 already-imported contacts (matching existing `Contact` rows to
     their `resourceName` via the same phone/name heuristics used today, one
     time, to backfill `contact_google_links`) before incremental sync can
     rely on ID matching exclusively.
   - Whether deletions/merges on the Google side should ever propagate into
     Lenie automatically, or only ever surface as a reviewable suggestion
     (consistent with this project's general "propose, human confirms"
     posture — see ADR-026's auto-detection design for the precedent).

## Alternatives considered

- **Keep the single `google_contact_resource_name` column, just start
  writing to it.** Rejected: cannot represent one `Contact` linked to two
  Google accounts, which is the user's actual situation today, not a
  hypothetical future one.
- **Continue CSV-only import indefinitely, invest instead in loosening the
  name-matching heuristics** (fuzzy match, nickname dictionary). Rejected as
  the primary fix: papers over the real problem (no stable ID) with more
  guessing, which is the opposite direction from what the 2026-09-23 review
  session showed was needed — the false conflicts came from trusting
  name/phone as identity, not from the fuzziness of the matching function
  itself.

## Consequences

- A new table (`contact_google_links`) and a removed column
  (`google_contact_resource_name`) — small, additive migration.
- Real Google API integration means OAuth token storage/refresh for
  (potentially) two accounts, not one — reuse `library/google_auth.py`,
  extend it for multi-account token storage if it does not already support
  that.
- Once linked, future imports for a previously-seen contact skip the
  name/phone heuristic entirely and become a no-conflict update — the 13/453
  false-conflict rate seen in the CSV-based run should not recur for any
  contact that has been through one successful link.
- Does **not** by itself resolve pre-existing data-quality problems already
  sitting in Google Contacts (typos, maiden-name duplicates, one phone
  number shared by two people) — those still need either manual cleanup at
  the source or Lenie's separate maiden/former-name feature.

## Related work (not in scope here, tracked separately)

- Maiden name / former surname support on `Contact` — a sibling problem
  surfaced in the same 2026-09-23 review (e.g. "Małgorzata Kulińska" /
  "Małgorzata Michalska", same phone, married-name change), but a distinct
  data-model question (how Lenie represents a person's own name history)
  from this ADR's identity-matching-with-Google question. Do not fold the
  two together; resolve independently and cross-link if useful once both
  exist. (Tracked ad hoc as of 2026-09-23; check for a PR/ADR implementing
  it — e.g. PR #730 — before starting fresh.)

## Prompt for the implementing session

```
W backend/library/db/models.py Contact ma kolumnę google_contact_resource_name
(String, unique) opisaną jako "placeholder for a future Google Contacts sync
(no sync logic exists yet)" — nic jej dziś nie wypełnia ani nie
synchronizuje. Import z Google Contacts dziś działa wyłącznie przez ręczny
eksport CSV (backend/imports/google_contacts_import.py), który dopasowuje
kontakty po znormalizowanym numerze telefonu, a w drugiej kolejności po
znormalizowanej parze first_name+last_name. Ten CSV NIE zawiera żadnego
stabilnego ID kontaktu (potwierdzone: brak kolumny resourceName/id w
eksporcie) — dopasowanie po nazwie/telefonie generuje fałszywe konflikty
("ten sam telefon, ale różne nazwy") przy zwykłych literówkach, zdrobnieniach
(Baśka/Barbara) czy dopiskach w polu nazwiska (np. "(OSM)").

Przeczytaj najpierw docs/adr/adr-028-google-contacts-api-sync.md (ten plik) —
zawiera pełny kontekst decyzji i jest w stanie "Proposed", czeka na
implementację. Zaimplementuj go:

1. Integracja z Google People API (OAuth) zamiast ręcznego CSV jako
   podstawowy mechanizm sync — backend/library/google_auth.py ma już
   podstawy OAuth 2.0 do rozbudowy.

2. Zamiast kolumny google_contact_resource_name na Contact — osobna tabela
   contact_google_links (contact_id FK, google_account, resource_name,
   UNIQUE(google_account, resource_name)), wzorem już istniejących
   ContactAddress (backend/library/db/models.py:3326) i ContactOrganization
   (:3347) — "jeden kontakt, wiele powiązań z rolą". Usuń kolumnę
   google_contact_resource_name (nigdy nie była wypełniana — bezpieczne do
   usunięcia bez migracji danych).

3. Rozstrzygnij i zaimplementuj otwarte pytania z sekcji "Decision" pkt 3
   ADR-a: model synchronizacji per-konto vs. jednym przebiegiem, obsługa
   konfliktu danych między dwoma kontami tej samej osoby (czy potrzebny
   wskaźnik pochodzenia per pole/zmiana, podobnie jak discovery_sources dla
   Document), czy potrzebny jednorazowy backfill łączący istniejące ~480
   kontaktów z ich resourceName przed przejściem w pełni na sync po ID,
   oraz czy usunięcia/scalenia po stronie Google mają kiedykolwiek
   propagować się automatycznie, czy zawsze tylko jako propozycja do
   zatwierdzenia przez człowieka (spójnie z resztą projektu — patrz
   ADR-026 auto-detekcja jako precedens).

Po zakończeniu zaktualizuj status tego ADR-a na "Accepted — implemented in
the same change" (wzorem ADR-026), z datą i krótkim podsumowaniem, co
faktycznie zostało zdecydowane w otwartych pytaniach.

Nie mieszaj tego z osobnym tematem "nazwisko panieńskie" (patrz sekcja
"Related work" w tym ADR-ie) — to świadomie odrębny problem; sprawdź, czy
PR #730 już go implementuje, zanim zaczniesz od zera.

To projekt Lenie (backend/CLAUDE.md, backend/library/CLAUDE.md,
backend/imports/CLAUDE.md mają pełny kontekst). Konwencje: uv (nigdy pip),
feature branch + PR do main (nigdy commit na main), zmiany bazodanowe testować
na bazie NAS (192.168.200.7:5434), po wdrożeniu backendu zawsze
bash nas-deploy.sh backend.
```
