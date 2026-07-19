# Hybrid document search

`GET /search` (frontend `web_interface_react`) is backed by `SearchService.search_similar()`
(`backend/library/search_service.py`), which combines two independent signals for the same
query text:

- **Lexical candidates** — `DocumentRepository.search_text()`
  (`backend/library/document_repository.py`): a plain SQL `ILIKE` scan over
  `title`/`tags`/`note`/`text`.
- **Semantic candidates** — `DocumentRepository.get_similar()`: pgvector cosine search over
  `websites_embeddings`.

`SearchService._merge_results()` de-duplicates by document, scores each candidate from whichever
signal(s) found it, and returns the top `limit` documents. Both the SQL layer and this Python
scoring layer independently "fold" query/document text into a comparable form, and — this is the
part that bit us in practice — **the two foldings have to agree**, or a document can be found by
one layer and then scored as a non-match by the other.

## Why plain `ILIKE` is not enough

`search_text()` requires every query token (≥3 chars) to appear literally, via
`ILIKE '%token%'`, somewhere in the document's searchable text (see the `and_(...)` clause). That
is deliberately simple — no PostgreSQL full-text-search migration, no ranking infrastructure — but
it has a sharp edge: **`ILIKE` compares bytes, not meaning.** Two classes of query/document
mismatch defeat it:

1. **Diacritics.** Polish text is full of accented letters (ą, ć, ę, ł, ń, ó, ś, ź, ż). Users
   routinely type queries without them — no Polish keyboard layout, muscle memory from English
   input, or just habit. `ludzmi ILIKE '%ludzmi%'` will never match a document that only contains
   `ludźmi`, because `ILIKE` performs no accent folding at all. This is not a rare edge case, it's
   the default way many users type.
2. **Inflection.** Polish is a heavily inflected language: `Afryka` / `Afryki` / `Afryce` /
   `Afrykę` are all "the same" word to a human, but four different literal strings to `ILIKE`.
   This class of mismatch is **not** fixed by this change (see [Known limitations](#known-limitations)).

Because `search_text()` ANDs all tokens together, a single unmatched token — even one out of
three or four — drops the entire document from the candidate list, no matter how well the rest of
the query matches. That combination (diacritic-insensitive matching missing + all-tokens-required)
is what made document 9210 ("W Dubaju obsługiwały mężczyzn...", which discusses handel ludźmi w
Afryce at length) invisible to the query `handel ludzmi w afryce`: the token `ludzmi` never
literally occurs in a document that only ever spells it `ludźmi`, so the AND-clause failed and the
document never became a lexical candidate — even though `handel` and `afryce` did match verbatim
elsewhere in the text.

## Why not a heavier solution?

The obvious "proper" fixes are bigger than this problem warrants:

- **PostgreSQL full-text search** (`tsvector`/`tsquery` with a Polish dictionary) would solve
  both diacritics *and* inflection via stemming, but needs a dictionary/config decision, a
  generated column + GIN index, and a schema migration — a much larger change for a query volume
  that doesn't currently need FTS-grade ranking.
- **A hand-rolled `translate()` accent map** (mapping each accented letter to its plain
  equivalent via SQL `translate()`) works, but duplicates a mapping table that already exists,
  correctly, as a PostgreSQL contrib extension.

Instead, this fix reuses **`unaccent`**, a PostgreSQL contrib extension that was already installed
in `database/init/02-create-extension.sql` (alongside `pgvector` and `pg_trgm`) but — until this
change — never actually wired into a query. `unaccent()` strips diacritics using PostgreSQL's own
built-in Latin transliteration rules, including letters that have no Unicode decomposition (e.g.
`ł` → `l`, which `unicodedata.normalize("NFKD", ...)` in Python leaves untouched — see below).

`search_text()` now wraps **both sides** of every `ILIKE` comparison — the document's searchable
text and the query pattern — in `func.unaccent(...)`:

```python
searchable = func.unaccent(func.concat_ws(" ", ...))
phrase = func.unaccent(f"%{query}%")
conditions = [title.ilike(phrase), searchable.ilike(phrase)]
```

This still performs an unindexed sequential scan (same as before — no index change), it just folds
accents on the fly before comparing. Given the current document volume that's an acceptable
trade-off for not introducing FTS infrastructure.

## The second layer: `SearchService._normalise()`

Even after `search_text()` finds a document as a lexical candidate, `_merge_results()` computes a
`text_score` by re-tokenizing the query and the candidate's title/body **in Python**
(`SearchService._normalise()`) and checking token/substring overlap. This is a *separate*
normalization step from the SQL one above, and it had its own, independent diacritics bug:

```python
# before the fix
value = unicodedata.normalize("NFKD", value or "")
return " ".join(re.findall(r"[\w]+", value.casefold()))
```

`NFKD` decomposes an accented letter into a base letter plus a *combining* diacritical mark (e.g.
`ź` → `z` + U+0301 COMBINING ACUTE ACCENT). The bug: that combining mark is **not** matched by
`\w` (`str.isalnum()` returns `False` for it), so `re.findall(r"[\w]+", ...)` treats it as a
token boundary. `ludźmi` didn't fold to `ludzmi` — it silently split into two separate tokens,
`ludz` and `mi`. The query token `ludzmi` (typed as one word) could then never appear as a
substring of the normalized document text, so this layer scored the token as absent even for a
document that *did* contain the word — the normalization was a no-op for exactly the case it was
supposed to handle.

The fix strips combining marks after decomposition (the standard accent-folding idiom), and adds
an explicit translation for `ł`/`Ł` (which, like in `unaccent`, has no Unicode canonical
decomposition, so NFKD alone can't fold it) to keep this Python-side folding consistent with the
SQL-side `unaccent()`:

```python
_EXTRA_FOLD = str.maketrans({"ł": "l", "Ł": "L"})

value = (value or "").translate(_EXTRA_FOLD)
value = unicodedata.normalize("NFKD", value)
value = "".join(ch for ch in value if not unicodedata.combining(ch))
return " ".join(re.findall(r"[\w]+", value.casefold()))
```

**Why two separate implementations instead of one shared function?** The SQL layer runs inside
PostgreSQL (it has to, to avoid pulling every document's full text into Python just to filter it)
and uses `unaccent()`; the Python layer runs after documents are already loaded, scoring already-
selected candidates, and uses `unicodedata`. They don't share a runtime, so they can't share code
— but they *must* stay behaviorally aligned, or a document can pass one layer's folding and fail
the other's. Any future change to one folding rule (e.g. adding another non-decomposable letter)
should be mirrored in the other.

## A third bug: scoring against the wrong window

Fixing both foldings above was enough to make document 9210 a lexical candidate again, but it
still didn't reliably surface in the UI: `search_text()`'s returned dict truncates the document
body to `doc.text[:1000]` (originally so a `/search` response snippet doesn't ship an entire
article per hit). `_merge_results()` reused that same truncated field to *compute* `text_score`.
For document 9210 the first 1000 characters are portal boilerplate and an AI-generated summary
paragraph — `handel` and `afryce` (the literal forms the query needed) don't occur until later in
the article, even though the full 9.4k-character text clearly contains all three query tokens.
Coverage computed against the 1000-char window was 1/3; against the full text it's 3/3.

The fix separates the two concerns: `search_text()` now also returns an untruncated
`text_for_scoring` field (no extra DB read — `doc.text` is already loaded on the ORM object), used
only inside `_merge_results()`'s coverage/phrase calculations and popped before the result is
returned to the API (same as `tags`/`note`), so response payload size is unaffected. The display
`text` field stays truncated at 1000 chars.

## Rebalancing lexical vs. semantic scoring

Even with 3/3 token coverage, the pre-existing formula

```python
text_score = min(1.0, 0.45 * coverage + 0.35 * title_coverage
                 + 0.20 * phrase_in_body + 0.35 * phrase_in_title)
```

caps a pure body-coverage match (no title hit, no exact phrase) at `0.45` — below the `~0.50-0.55`
that ordinary semantic (embedding) hits get for merely topic-adjacent articles. Verified against
the live NAS deployment: after both fixes above, document 9210 (3/3 coverage) scored `0.45` and
ranked **82nd** for `handel ludzmi w afryce` — technically findable, practically invisible (the
frontend's search page tops out at `limit=50`).

This is a scoring-weight decision, not a bug, and it affects ranking for every query — so it was
confirmed with the project owner before changing. The `coverage` weight was first raised to `0.60`
(later revised to `0.70` below, once `coverage` itself stopped being a trivial 0/1 value).

## A fourth bug: plain-presence coverage can't discriminate between lexical candidates at all

Raising the weight uncovered a worse problem. `search_text()`'s SQL layer already requires **every**
query token to be present via an `AND` of `ILIKE` clauses (see [Why plain `ILIKE` is not
enough](#why-plain-ilike-is-not-enough)) — so *by construction*, every document `search_text()`
returns has 3/3 plain-presence coverage. Plain presence is therefore not a signal at all for lexical
candidates: it's always `1.0`, so `0.60 * coverage` was really just adding a flat `0.60` to *any*
lexical candidate, indiscriminately.

That surfaced immediately on the next query: `handel narkotykami w afryce` put a Polish
organized-crime article ("Meksykański kartel i albańska mafia w Polsce") **#1**, ahead of the
one article actually about drug trafficking in Africa ("Grupa Wagnera... Powstało tam imperium
narkotykowe", found only via semantic search). Why: "handel narkotykami" ("drug trafficking") is
a generic, frequently-recurring phrase in Polish crime reporting — it appeared once in that
unrelated article — and "Afryka" happened to be mentioned once too, ~2860 characters away, in a
completely different paragraph about unrelated business dealings. Three tokens, three literal
hits, `coverage = 1.0`, same as a document genuinely about the query.

**First attempt (discarded): window/proximity-based coverage.** The intuitive fix is to require
query tokens to co-occur near each other — score the best-matching ~500-character window instead
of "anywhere in the document". This was implemented and tested, and it does suppress the
`handel narkotykami` false positive (its two matched tokens are ~2860 characters apart, well
outside any reasonable window). But it also suppressed document 9210 itself: a real, well-written
article naturally varies its phrasing across paragraphs rather than repeating the same sentence —
9210 mentions "Afryka" (in some inflected form) near the start, "ludźmi" nearby, but the literal
form `afryce` only much later in the piece, addressing a different aspect of the same story. The
token span in the *genuinely relevant* document (~5980 characters) was actually **wider** than in
the *false positive* (~2860 characters). Proximity punished true positives about as much as false
ones — it measures physical distance, not topical relevance, and those turned out not to
correlate here.

**What actually discriminates: occurrence frequency.** A document that is genuinely *about* the
query tends to repeat its key vocabulary throughout, in different inflected forms, because that's
how articles are written — not because the words are physically adjacent. Checked directly on NAS:
in document 9210, the stem "afryk-" occurs 6 times and "handl-" 8 times across the text; in the
"Meksykański kartel" false positive, "afryk-" occurs once and "handl-" twice. That gap is the real
signal. `SearchService._token_coverage()` replaced plain presence with an occurrence-weighted
average, saturating at `_TOKEN_SATURATION = 2` occurrences (so a token doesn't need to repeat
indefinitely to get full credit, and a single very-repetitive word can't dominate the average):

```python
@classmethod
def _token_coverage(cls, body: str, tokens: set[str]) -> float:
    return sum(min(1.0, body.count(t) / cls._TOKEN_SATURATION) for t in tokens) / len(tokens)
```

With `coverage` no longer trivially `1.0` for every lexical candidate, the weight was raised again,
from `0.60` to `0.70`, to keep a genuinely on-topic match (`coverage` typically `~0.7-0.9` once
occurrence-weighted) competitive with semantic hits, while a one-off incidental match (`coverage`
typically `~0.5-0.7`) stays below the usual semantic threshold:

```python
text_score = min(1.0, 0.70 * coverage + 0.35 * title_coverage
                 + 0.20 * phrase_in_body + 0.35 * phrase_in_title)
```

Re-verified on NAS for both queries at once: document 9210 ranks **#1** (`0.583`) for
`handel ludzmi w afryce`, and the "Meksykański kartel"/"Nowa ulubienica Putina" false positives
have both dropped out of the top 10 for `handel narkotykami w afryce` — the top result there is
now the genuinely relevant Wagner-Group-in-Africa article (semantic match, `#3`, since it doesn't
literally contain the word "narkotykami" — it says "narkotykowe" — so it never becomes a lexical
candidate at all; this is the inflection limitation below).

## Known limitations

- **Inflection/stemming is still unsolved.** This fix only folds diacritics, not word endings. A
  query for `afryka` (nominative) against a document that only ever uses inflected forms
  (`afryki`/`afryce`/`afrykę`) would still fail to become a lexical candidate, and `narkotykami`
  won't match a document that only ever says `narkotykowe`. Solving this properly needs Polish
  morphological stemming (e.g. a `tsvector` config with an `ispell`/Morfologik dictionary), which
  is the "heavier" FTS migration this change deliberately avoided. Not currently tracked as a
  backlog item.
- **Geographic tags (`kraj-*`) are not used by search at all**, despite the codebase already having
  country/place detection (`country_gazetteer.py`, `article_tagging.py`, geocoded
  `document_entities`). Investigated as a possible complementary signal for queries like "w
  Afryce": not worth pursuing yet — only 73/9215 documents (0.8%) carry any `kraj-*` tag (the
  tagging pipeline has only run on documents that went through chunk analysis), and the gazetteer
  covers individual countries, not continents ("Afryka" itself has no entry). Revisit once the
  tagging pipeline has run over most of the corpus and continents/regions are added to the
  gazetteer.

## Wydajność — pomiary i decyzje Etapu 12 (2026-07-19, NAS, 9220 dokumentów / 3062 embeddingi)

Zmierzone `EXPLAIN (ANALYZE)` na bazie NAS:

| Zapytanie | Czas | Plan |
|---|---:|---|
| Filtr daty publikacji (`published_on >=` + typ) | 0,7 ms | index scan (`idx_documents_published_on`) |
| Filtr okresu treści (EXISTS na `document_time_periods`) | 0,3 ms | index (`idx_document_time_periods_document_chapter`) |
| Filtr autora (EXISTS `document_persons` role=author + `persons`) | 2,4 ms | index |
| Filtr języka | 0,2 ms | — (9220 wierszy, nieistotne) |
| Wektorowa top-10 (`<=>` gemma2) | **207 ms** | **seq scan** — patrz niżej |
| Leksykalna (`unaccent(...) ILIKE` po title+tags+note+text) | **1404 ms** | seq scan po całych treściach — patrz niżej |

**Decyzja: zostajemy przy ILIKE (bez FTS/GIN) — z progiem rewizji.** Uzasadnienie:
1. Leg leksykalny (1,4 s) działa równolegle znaczeniowo z legiem wektorowym, którego łączny czas
   i tak dominuje zdalne generowanie embeddingu zapytania (~5 s, CloudFerro). Przy obecnym
   korpusie przyspieszenie SQL nie zmienia odczuwalnej latencji `/search`.
2. `pg_trgm` GIN wymaga niemutowalnej otoczki na `unaccent()` (funkcja jest STABLE) i indeksu po
   wyrażeniu identycznym z zapytaniem — po pełnych treściach książek indeks byłby duży i wolno
   budowany; pełny FTS (`tsvector`) bez polskiego stemmingu (Morfologik/ispell) pogorszyłby
   semantykę substring-match, którą obecnie mamy (patrz „Known limitations").
3. **Próg rewizji:** leg leksykalny > 3 s albo korpus > 25 tys. dokumentów → wtedy `pg_trgm` GIN
   z otoczką `immutable_unaccent()` na wyrażeniu z `search_text()` (mniejsze ryzyko niż FTS,
   zachowuje substring-match), a stemming rozważyć osobno razem z Morfologikiem.

**Decyzja: brak indeksu HNSW dla aktywnego modelu embeddingów — świadomie.** Model
`BAAI/bge-multilingual-gemma2` ma **3584 wymiary**, powyżej limitu 2000 wymiarów HNSW dla typu
`vector` w pgvector (stąd istnieją indeksy `idx_emb_*` tylko dla starych, mniejszych modeli).
Seq scan po 3048 wektorach = 207 ms — akceptowalne. **Próg rewizji:** > 25 tys. embeddingów
gemma2 albo > 1 s → indeks HNSW po rzutowaniu `halfvec(3584)` (pgvector ≥ 0.7 wspiera do 4000
wymiarów dla halfvec; wymaga zmiany wyrażenia w `get_similar()` na identyczne z indeksem —
`embedding::halfvec(3584) <=> zapytanie::halfvec(3584)` — i akceptacji fp16).

**Porządki wykonane w Etapie 12:** usunięty `/website_similar` (slack_bot zmigrowany na jawny
wariant `POST /search` — bez wywołania LLM) wraz z `SearchService.search_similar()`;
`/ai_parse_intent` ZOSTAJE (slack_bot aktywnie używa go do klasyfikacji komend DM — warunek
„brak innych konsumentów" niespełniony); `get_list()` dostał tiebreaker `id` w sortowaniu
(stabilna paginacja przy identycznych timestampach); raporty: `imports/search_reports.py`
(interpretacje + koszty LLM + alert `cost_status='unknown'`/brak wpisu w `llm_pricing`,
exit code 2 przy alercie — nadaje się na cron).
