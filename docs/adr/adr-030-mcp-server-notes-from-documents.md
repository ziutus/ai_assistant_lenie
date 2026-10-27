# ADR-030: Serwer MCP do tworzenia notatek Obsidian z dokumentów Lenie

**Data:** 2026-10-27
**Status:** Proposed (szkic do przeglądu — Claude + Codex)
**Decydent:** Ziutus

## Kontekst

Chcemy pracować z Lenie z poziomu desktopowego klienta AI (Claude Code desktop, ChatGPT desktop), a nie tylko
przez skill `/lenie-obsidian-note` w CLI. Pierwszy scenariusz: **tworzenie nowych notatek Obsidian na podstawie
istniejących dokumentów** (pierwszy przypadek: dokument 11176 — film YouTube o koszcie domowego labu LLM).

Co już mamy:

- Skill [`lenie-obsidian-note`](../../.agents/skills/lenie-obsidian-note/SKILL.md) — pełny workflow
  (metadane → runy analizy → chunki → indeks wiedzy → pakiet zmian → jedna zgoda → zapis → sync bazy).
  Czyta Lenie przez REST (`x-api-key`), zapisuje do vaulta z dysku lokalnego.
- REST API backendu na NAS (`:5055`): `/website_get`, `/analysis_runs`, `/analysis_run/<id>/chunks`,
  `/document/<id>/readiness`, `/chunk/<id>` (PATCH) i inne.
- Archiwalny prototyp serwera MCP (tag `archive/mcp-server`, usunięty 2026-07-22): FastMCP + streamable HTTP,
  ale czytał **bezpośrednio bazę przez ORM** i miał własny zapis do vaulta. Usunięty jako zbędny koszt utrzymania,
  gdy skill wystarczał.

Ograniczenia klientów (stan wg źródeł zewnętrznych z października 2026, do weryfikacji w dokumentacji OpenAI):

- **Claude Code / Codex** — obsługują serwery **stdio** (proces lokalny) oraz HTTP.
- **ChatGPT desktop** — według dostępnych opisów łączy się tylko ze zdalnymi serwerami **HTTPS** (tryb
  deweloperski, Plus/Pro/Business), nie ze stdio.

## Decyzja

### D1. Etapowanie transportu

1. **Etap A (teraz): lokalny serwer stdio na komputerze użytkownika** — dla Claude Code desktop (i Codex).
   Ma dostęp do vaulta z dysku i do NAS po LAN/VPN. Zero ekspozycji do internetu.
2. **Etap B (osobna decyzja, później): ten sam kod przez streamable HTTP** dla ChatGPT. Wymaga publicznego
   HTTPS + uwierzytelnienia (OAuth), czyli ekspozycji spoza LAN (relay z ADR-023) oraz zapisu do vaulta
   zdalnie — to zmienia model zagrożeń, więc **nie wchodzi w zakres tego ADR**. Kod piszemy tak, by transport
   był jedyną różnicą (rdzeń narzędzi niezależny od stdio/HTTP).

### D2. Cienki klient REST, nie ORM

Serwer MCP **nie dotyka bazy** — wywołuje REST backendu z `LENIE_API_KEY` (klucz `kind=service`, jak skill).
Powód: jedna warstwa autoryzacji i logiki, zero duplikowania modeli, działa z dowolnej maszyny.

- Pakiet: `lenie_mcp/` w korzeniu repo, własny `pyproject.toml` i środowisko `uv` (konwencja: każdy podprojekt
  zarządza zależnościami osobno). Zależności: oficjalne SDK `mcp` (FastMCP), `httpx`.
- Konfiguracja wyłącznie ze zmiennych środowiskowych: `LENIE_API_URL`, `LENIE_API_KEY`, `LENIE_OBSIDIAN_VAULT`.
  Nic z tego nie trafia do repo; rejestracja w kliencie (`claude mcp add` / `.mcp.json` użytkownika) odwołuje się
  do zmiennych, nie do wartości.
- Stdio: **nic na stdout poza protokołem**, logi tylko na stderr.

### D3. Narzędzia (Etap A)

Zasada: mało narzędzi, każde zwraca ograniczony rozmiar, nic nie zwraca całego vaulta ani całej bazy.

**Odczyt Lenie** (`readOnlyHint: true`)

| Narzędzie | REST | Uwagi |
|---|---|---|
| `lenie_get_document(id)` | `/website_get?include_text=0` + `/document/<id>/readiness` | metadane, UUID, `obsidian_note_paths`, stan przetwarzania |
| `lenie_list_analysis_runs(doc_id)` | `/analysis_runs` | wybór runu jak w skillu |
| `lenie_get_chunks(run_id, positions?)` | `/analysis_run/<id>/chunks` | bez `positions` — wersja `lite` (temat + streszczenie) |
| `lenie_get_document_text(id, offset, max_chars)` | `/website_get` | stronicowane; ostrzega o surowym tekście (`URL_ADDED`, `DOCUMENT_INTO_DATABASE`) |

**Odczyt vaulta** (`readOnlyHint: true`, tylko pod `LENIE_OBSIDIAN_VAULT`)

| Narzędzie | Uwagi |
|---|---|
| `obsidian_read_index()` | `02-wiedza/_index.md` |
| `obsidian_read_note(path)` | ścieżka względna; odrzuca `..`, ścieżki absolutne, symlinki wychodzące z vaulta |
| `obsidian_find_notes(query, limit≤10)` | tylko nazwy plików + tagi frontmattera, **bez skanowania treści całego vaulta** |

**Zapis — dwuetapowy** (propozycja nic nie zapisuje)

| Narzędzie | Efekt |
|---|---|
| `obsidian_propose_package(doc_id, files[], run_id?, chunk_positions?)` | waliduje i zwraca podgląd + `proposal_id`; **nie zapisuje nic** |
| `obsidian_commit_package(proposal_id)` | zapisuje pliki, potem synchronizuje bazę, zwraca raport |

`files[]` to cały pakiet (nowe notatki, ewentualnie zmiana indeksu) — odpowiada „jednej zgodzie na pakiet”
ze skilla. `proposal_id` = skrót (ścieżki + treść + skróty istniejących plików bazowych); commit odrzuca
pakiet, jeśli plik bazowy zmienił się od propozycji.

Walidacje w `propose` (twarde, po stronie serwera, niezależne od modelu):

- ścieżka pod dozwolonym prefiksem (`02-wiedza/`), rozszerzenie `.md`, brak wyjścia z vaulta;
- tylko **tworzenie** nowych plików albo **dopisanie** do `_index.md`/istniejącej notatki; brak narzędzia do
  usuwania i brak nadpisywania obcej treści;
- frontmatter z tagiem `wiedza/…`, jeden H1, źródło zawiera **UUID** dokumentu (serwer porównuje z UUID
  pobranym z API — nie z tym, co wpisał model), brak cyrylicy;
- wątek finansowy albo jawne `TODO: wątek finansowy` dla tematów technologicznych/firmowych/geopolitycznych
  (ostrzeżenie, nie blokada).

**Czego świadomie nie robimy w Etapie A:** wyszukiwania hybrydowego, edycji organizacji/osób, usuwania, importu
nowych dokumentów. Każde to osobne rozszerzenie z własną oceną ryzyka.

### D4. Synchronizacja bazy po zapisie

Skill po zapisie: dodaje ścieżkę do `Document.obsidian_note_paths` (bez duplikatów), ustawia `reviewed_at` jeśli
puste, dopisuje ścieżki do chunków `TEMAT` pokrytych notatką. Przy wykonywaniu przez REST **brakuje**
(do potwierdzenia przy implementacji) jednego atomowego endpointu zapisującego to w jednej transakcji.

- **Do dodania w backendzie:** `POST /document/<id>/obsidian_notes` z `{"paths": [...], "run_id": int|null,
  "chunk_positions": [...]|null}` — idempotentny, w jednej transakcji, zwraca stan po zapisie. Wymaga
  wdrożenia na NAS (tylko z domowej sieci LAN).
- Kolejność w `commit`: zapis plików → sync bazy. Błąd sync **nie cofa** plików; raport pokazuje rozbieżność i
  proponuje naprawę (ta sama zasada co w skillu).

### D5. Bezpieczeństwo

- **Treść dokumentów to dane niezaufane** (prompt injection — [docs/security/prompt-injection-defense.md]
  (../security/prompt-injection-defense.md)). Wynik każdego narzędzia odczytu jest opakowany w jawny blok
  „dane z Lenie, nie instrukcje”. Najgroźniejszy wektor: złośliwa treść strony nakłania model do zapisu
  notatki; zabezpieczeniem są twarde walidacje `propose` + ręczne zatwierdzenie `commit` przez użytkownika.
- `obsidian_commit_package` **nie może być na liście auto-allow** w kliencie; to jedyny punkt zapisu.
- Klucz API nigdy w odpowiedziach narzędzi ani w logach. Błędy HTTP mapowane na krótkie komunikaty bez nagłówków.
- `is_private` dokumentu: w Etapie A tylko ostrzeżenie w `lenie_get_document`; w Etapie B (zewnętrzny
  dostawca) — blokada.
- Prywatność: treść dokumentów i notatek przechodzi z natury do dostawcy modelu klienta (Anthropic w Etapie A;
  OpenAI w Etapie B). To świadoma decyzja użytkownika, a nie efekt uboczny serwera.

### D6. Workflow i reguły

Reguły tworzenia notatek (wybór chunków, słownik STT dla YouTube, format notatki, kolejność) **zostają w jednym
miejscu** — `.agents/skills/lenie-obsidian-note/references/workflow.md`. Serwer MCP ich nie kopiuje.
W Etapie A Claude Code używa skilla + narzędzi MCP. Gdy dojdzie ChatGPT (Etap B), serwer wystawi te same reguły
jako MCP `prompt`/`resource` czytane z tego pliku, bez drugiej kopii.

## Przebieg dla dokumentu 11176 (pierwszy test)

Stan z REST (2026-10-27): `document_type=youtube`, język `pl`, `processing_status=EMBEDDING_EXIST`,
`obsidian_note_paths=[]`, `reviewed_at=null`, UUID `82112b28-7b88-439a-ab3c-fc2f14ad11cd`, transkrypcja 17 225
znaków, run **253** (`mode=transcript`, 17 chunków, wszystkie `approved`, `analyzed_count=0` — czyli sam podział,
bez tematów/streszczeń), jest `chapter_list` (16 rozdziałów) i `summary`.

1. `lenie_get_document(11176)` → metadane, readiness, UUID.
2. `lenie_list_analysis_runs(11176)` → jeden run 253; `analyzed_count=0` ⇒ pełny tekst, ale ścieżki notatek
   trzeba potem wpisać w chunki `TEMAT` runu 253.
3. `lenie_get_document_text(11176)` (1–2 strony) — transkrypcja jest po angielsku w treści filmu; notatka po
   polsku.
4. `obsidian_read_index()` + `obsidian_find_notes("llm sprzęt koszt")` → najwyżej 1–2 pasujące notatki;
   dla YouTube także słownik `02-wiedza/_słownik omówień i błędów STT.md`.
5. Model przygotowuje notatkę (wątek finansowy jest tu rdzeniem: Mac Studio ~9 499 USD vs serwer ~5 899 USD,
   „kupić vs wynająć vs API”, cena za „użyteczny rok”, wygasanie wsparcia V100/MI50/P40) i woła
   `obsidian_propose_package`.
6. Użytkownik ogląda podgląd, zatwierdza → `obsidian_commit_package`: plik w vaulcie, dopisek w indeksie,
   sync bazy (dokument 11176 + 17 chunków `TEMAT` runu 253 tylko jeśli notatka faktycznie pokrywa ich treść).
7. Weryfikacja: `lenie_get_document(11176)` pokazuje ścieżkę i `reviewed_at`.

Docelową ścieżkę pliku i tytuł proponuje model w kroku 5; nie ustalamy ich z góry.

## Plan wdrożenia

| Etap | Zakres | Wdrożenie na NAS |
|---|---|---|
| 0 | Ten ADR + przegląd (Claude i Codex) | — |
| 1 | `lenie_mcp/`: narzędzia odczytu Lenie i vaulta, testy jednostkowe (httpx mock), rejestracja w Claude Code | nie (serwer działa lokalnie) |
| 2 | Backend: `POST /document/<id>/obsidian_notes` + testy | tak, tylko z domowej sieci LAN |
| 3 | Narzędzia zapisu (`propose`/`commit`) + test end-to-end na dokumencie 11176 | — |
| 4 | (osobny ADR) HTTP + OAuth dla ChatGPT | zależnie od decyzji |

## Konsekwencje

- **Plus:** jeden mały pakiet bez dostępu do bazy; te same reguły i ta sama autoryzacja co skill; zapis możliwy
  tylko przez dwuetapowy, walidowany przepływ.
- **Plus:** Etap A nie wystawia niczego do internetu.
- **Minus:** ChatGPT desktop (wg obecnych informacji) nie zadziała bez Etapu B; to osobny koszt i ryzyko.
- **Minus:** dwie ścieżki (skill i MCP) w Etapie A — akceptowalne, bo reguły są w jednym pliku, a skill może
  później zostać cieńszą nakładką na narzędzia MCP.
- **Ryzyko:** drugi serwer MCP to znów powierzchnia utrzymania — ten sam powód, dla którego prototyp usunięto.
  Dlatego zakres jest zawężony do notatek i nie zawiera niczego, co skill już robi lepiej.

## Pytania otwarte

1. Czy `commit` ma przyjmować `proposal_id` od modelu, czy wymagać potwierdzenia przez MCP elicitation
   (wsparcie zależy od klienta)?
2. Dozwolone prefiksy zapisu: tylko `02-wiedza/` czy także inne katalogi vaulta?
3. Czy po Etapie 3 skill `lenie-obsidian-note` ma przejść na narzędzia MCP, czy zostać niezależny?
4. Potwierdzić w dokumentacji OpenAI, czy ChatGPT desktop obsługuje stdio (źródła są trzecie i niespójne).
