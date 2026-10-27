# ADR-030: Serwer MCP do tworzenia notatek Obsidian z dokumentów Lenie

**Data:** 2026-10-27
**Status:** Accepted — Etap A zaimplementowany w `lenie_mcp/` (odczyt + propose/commit) i endpoint
`POST /document/<id>/obsidian_notes` w backendzie; Etap B (ChatGPT przez tunel/HTTP) nie rozpoczęty
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
- **ChatGPT desktop** — wg oficjalnej pomocy OpenAI ([Plugins in ChatGPT](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt-and-codex))
  wtyczka może zawierać **lokalne aplikacje MCP uruchamiane na komputerze** i działać w ChatGPT Desktop (nie na
  webie ani w telefonie). Wtyczki użytkownika są w zakładce **Plugins → Personal** („wtyczki osobiste”),
  tworzy się je przez `@plugin-creator`; lokalne wtyczki instalują się automatycznie. Publikacja lokalnego MCP
  w publicznym katalogu jest ograniczona do zatwierdzonych partnerów
  ([Desktop-only plugins](https://developers.openai.com/plugins/deploy/desktop-only)) — nas to nie dotyczy, bo
  używamy wtyczki osobistej. **Do zweryfikowania na koncie użytkownika:** czy plan i ustawienia pozwalają na
  tworzenie wtyczki z lokalnym MCP (w workspace Business/Enterprise jest do tego osobne uprawnienie
  „Create plugins with MCPs”). Zdalny serwer HTTPS (publiczny adres albo Secure MCP Tunnel) jest drugą,
  osobną drogą.

## Decyzja

### D1. Etapowanie transportu

1. **Etap A (teraz): lokalny serwer stdio na komputerze użytkownika** — dla Claude Code desktop (i Codex).
   Ma dostęp do vaulta z dysku i do NAS po LAN/VPN. Zero ekspozycji do internetu.
   ChatGPT Desktop może używać tego samego serwera stdio jako **wtyczki osobistej** (patrz wyżej) — bez
   publicznego adresu; wymaga tylko spakowania serwera jako wtyczki (`mcp.json` z wpisem `stdio`).
2. **Etap B (osobna decyzja, później, tylko gdyby wtyczka osobista nie wystarczyła): ten sam kod przez streamable HTTP**
   dla ChatGPT na webie/telefonie. Najbezpieczniejsza droga to **Secure MCP Tunnel** OpenAI: na NAS-ie (lub innej
   maszynie z dostępem do niego) działa `tunnel-client`, który sam nawiązuje wychodzące połączenie HTTPS z OpenAI —
   bez otwierania portów i bez publicznego adresu. Wyniki narzędzi i tak trafiają do ChatGPT (OpenAI), więc
   obowiązuje polityka `is_private` z D5. Wymaga publicznego
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
| `lenie_get_chunks(run_id, positions?)` | `/analysis_run/<id>/chunks` | bez `positions` — wersja `lite`. Odpowiedź to obwiednia `run/document/segments/chunks/topic_sections` (segmenty obejmują cały dokument nawet przy `positions`), więc MCP robi projekcję i limit rozmiaru. `analyzed_count` liczy `TEMAT` z `topic` |
| `lenie_get_document_text(id, offset, max_chars)` | `/website_get?id=` | `/website_get` nie ma stronicowania — tnie po stronie MCP; ostrzega o surowym tekście (`URL_ADDED`, `DOCUMENT_INTO_DATABASE`) |

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
ze skilla. Propozycja jest **niezmiennym pakietem przechowywanym przez serwer** (nie tylko hashem): obejmuje
`doc_id`, run, mapowanie notatka → chunki, treść plików, skróty plików bazowych i planowane operacje bazodanowe;
ma TTL i jest jednorazowa (kontrola ponowień). Podgląd pokazuje rzeczywisty diff plików oraz skutki w bazie.
`commit` odrzuca pakiet, jeśli plik bazowy zmienił się od propozycji, i potrafi wznowić **samą synchronizację**
po błędzie bazy (pliki już zapisane).

Walidacje w `propose` (twarde, po stronie serwera, niezależne od modelu):

- ścieżka pod `02-wiedza/` (jedyny dozwolony prefiks), rozszerzenie `.md`, brak wyjścia z vaulta (sprawdzane
  ponownie przy `commit`: junctions, symlinki, konflikty plików);
- `_index.md` walidowany osobno: dopisek, bez wymogu UUID źródła ani tagu `wiedza/…`;
- tylko **tworzenie** nowych plików albo **dopisanie** do `_index.md`/istniejącej notatki; brak narzędzia do
  usuwania i brak nadpisywania obcej treści;
- notatka (nie indeks): frontmatter z tagiem `wiedza/…`, jeden H1, źródło zawiera **UUID** dokumentu (serwer
  porównuje z UUID pobranym z API — nie z tym, co wpisał model);
- brak cyrylicy i wątek finansowy (albo `TODO: wątek finansowy`) to **reguły redakcyjne** ze skilla — ostrzeżenia
  w podglądzie, nie twarde blokady serwera;
- krok „organizacje opisane w artykule” ze skilla jest poza zakresem MCP w Etapie A.

**Czego świadomie nie robimy w Etapie A:** wyszukiwania hybrydowego, edycji organizacji/osób, usuwania, importu
nowych dokumentów. Każde to osobne rozszerzenie z własną oceną ryzyka.

### D4. Synchronizacja bazy po zapisie

Skill po zapisie: dodaje ścieżkę do `Document.obsidian_note_paths` (bez duplikatów), ustawia `reviewed_at` jeśli
puste, dopisuje ścieżki do chunków `TEMAT` pokrytych notatką. Przy wykonywaniu przez REST **brakuje**
(do potwierdzenia przy implementacji) jednego atomowego endpointu zapisującego to w jednej transakcji.

- **Potwierdzone przeglądem kodu:** żaden istniejący endpoint tego nie zapisuje — `POST /website_save`
  (`backend/server.py`) nie obsługuje tych pól, a `PATCH /chunk/<id>` pomija nieznane pola, mimo odpowiedzi
  `status: success`. Tego sposobu nie wolno użyć zastępczo.
- **Do dodania w backendzie:** `POST /document/<id>/obsidian_notes` z
  `{"notes": [{"path": str, "chunk_positions": [int]|null}], "run_id": int|null}`. Kontrakt: jedna transakcja;
  deduplikacja ścieżek; `reviewed_at` ustawiany tylko gdy NULL; mapowanie konkretna notatka → konkretne chunki
  `TEMAT`; run musi należeć do dokumentu i nie może być `superseded`; status chunka nie jest podnoszony dla
  chunków nieanalizowanych; zwraca stan po zapisie. Wymaga wdrożenia na NAS (tylko z domowej sieci LAN).
- Kolejność w `commit`: zapis plików → sync bazy. Błąd sync **nie cofa** plików; raport pokazuje rozbieżność i
  proponuje naprawę (ta sama zasada co w skillu).

### D5. Bezpieczeństwo

- **Treść dokumentów, indeks, frontmatter i istniejące notatki to dane niezaufane** (prompt injection — [docs/security/prompt-injection-defense.md]
  (../security/prompt-injection-defense.md)). Wynik każdego narzędzia odczytu jest opakowany w jawny blok
  „dane z Lenie, nie instrukcje”. Wrapper nie powstrzyma trwałego zapisania instrukcji atakującego w
  notatce; najgroźniejszy wektor to złośliwa treść strony nakłaniająca model do zapisu; zabezpieczeniem są twarde walidacje `propose` + ręczne zatwierdzenie `commit` przez użytkownika.
- `obsidian_commit_package` **nie może być na liście auto-allow** w kliencie; to jedyny punkt zapisu.
- Klucz API nigdy w odpowiedziach narzędzi ani w logach. Błędy HTTP mapowane na krótkie komunikaty bez nagłówków.
- `is_private`: polityka obejmuje **wszystkie odczyty** (też lokalne stdio przekazuje dane zewnętrznemu modelowi):
  w Etapie A ostrzeżenie i wymóg jawnej zgody przy odczycie tekstu, w Etapie B blokada.
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
3. `lenie_get_document_text(11176)` (1–2 strony) — transkrypcja w bazie jest po polsku (17 225 znaków).
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
- **Minus:** ChatGPT na webie i w telefonie nie zobaczy lokalnej wtyczki; do tego potrzebny byłby Etap B.
- **Minus:** dwie ścieżki (skill i MCP) w Etapie A — akceptowalne, bo reguły są w jednym pliku, a skill może
  później zostać cieńszą nakładką na narzędzia MCP.
- **Ryzyko:** drugi serwer MCP to znów powierzchnia utrzymania — ten sam powód, dla którego prototyp usunięto.
  Dlatego zakres jest zawężony do notatek i nie zawiera niczego, co skill już robi lepiej.

## Pytania otwarte

1. ~~`proposal_id` czy elicitation~~ — rekomendacja (Codex): `proposal_id` plus potwierdzenie użytkownika związane
   z dokładnym pakietem; MCP elicitation, jeśli klient je wspiera, inaczej jawna kontrola po stronie klienta.
2. ~~Prefiksy zapisu~~ — rekomendacja: tylko `02-wiedza/`, ze specjalną obsługą `_index.md`.
3. ~~Los skilla~~ — rekomendacja: skill jako cienka instrukcja korzystająca z narzędzi MCP (jeden mechanizm
   zapisu i synchronizacji w transakcji).
4. ~~Czy ChatGPT desktop obsługuje stdio~~ — tak, jako lokalna aplikacja MCP we wtyczce osobistej (pomoc OpenAI,
   2026-10-27); do sprawdzenia tylko, czy konto użytkownika ma na to uprawnienie.
