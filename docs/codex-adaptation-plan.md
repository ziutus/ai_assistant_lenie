# Plan dostosowania repozytorium do pracy z Codex

## Status dokumentu

- Status: propozycja do przeglądu
- Zakres: dokumentacja i konfiguracja pracy agentów
- Implementacja: poza zakresem tego dokumentu
- Główny cel: poprawić jakość, przewidywalność i bezpieczeństwo pracy Codex bez pogorszenia obsługi Claude Code

## 1. Kontekst

Repozytorium ma rozbudowaną dokumentację przygotowaną dla Claude Code:

- główny `CLAUDE.md`;
- lokalne pliki `CLAUDE.md` w komponentach;
- komendy w `.claude/commands/`;
- konfigurację serwerów MCP w `.mcp.json`;
- dokumentację architektury, ADR-y i materiały BMAD.

Codex nie korzysta natywnie ze wszystkich tych powierzchni. W szczególności wymaga własnego kontraktu repozytorium w `AGENTS.md`, używa `.codex/config.toml` do konfiguracji projektowej, a powtarzalne workflow najlepiej udostępniać jako skille w `.agents/skills/`.

Plan zakłada zachowanie istniejącej dokumentacji Claude Code oraz stopniowe dodanie warstwy wspólnej i natywnej dla Codex.

## 2. Cele

1. Zapewnić Codex krótki i jednoznaczny zestaw trwałych instrukcji.
2. Kierować agenta do właściwej dokumentacji zależnie od zmienianego komponentu.
3. Ujednolicić komendy instalacji, testowania, lintowania i budowania.
4. Ograniczyć ryzyko wykonania wdrożeń, migracji lub operacji chmurowych bez wyraźnego polecenia.
5. Zachować jedno źródło prawdy dla faktów wspólnych dla Claude Code i Codex.
6. Ograniczyć rozjazdy między dokumentacją a wykonywalną konfiguracją projektu.
7. Przenieść tylko wartościowe i faktycznie używane workflow Claude do natywnego formatu Codex.

## 3. Poza zakresem

Plan nie obejmuje:

- zmian kodu aplikacji;
- zmian architektury produkcyjnej;
- wdrożeń AWS, Kubernetes, Docker ani NAS;
- migracji bazy danych;
- instalowania nowych zależności aplikacji;
- masowej konwersji wszystkich komend BMAD;
- usuwania istniejącej obsługi Claude Code;
- automatycznego wykonywania commitów lub pushowania zmian.

## 4. Zidentyfikowane problemy

### 4.1. Brak natywnego kontraktu Codex

W repozytorium nie ma `AGENTS.md`. Codex nie otrzymuje więc automatycznie głównych reguł zapisanych w `CLAUDE.md` ani lokalnych instrukcji komponentów.

### 4.2. Nadmiar różnych rodzajów informacji w `CLAUDE.md`

Główny `CLAUDE.md` łączy:

- trwałe reguły pracy;
- opis architektury;
- komendy operacyjne;
- historię infrastruktury;
- dane zależne od wersji;
- konfigurację konkretnego środowiska Windows/WSL;
- konwencje specyficzne dla Claude Code.

Utrudnia to określenie, które instrukcje są obowiązkowe, a które mają charakter informacyjny.

### 4.3. Rozjazdy dokumentacji i konfiguracji

Podczas audytu znaleziono co najmniej następujące rozbieżności:

- `CLAUDE.md` wskazuje BSL 1.1, a `backend/pyproject.toml` deklaruje MIT;
- landing page jest opisana jako Next.js 14.2 i React 18, natomiast `package.json` używa Next.js 15 i React 19;
- główny `CLAUDE.md` opisuje dwie tabele, podczas gdy dokumentacja bazy obejmuje już większy model;
- ogólna komenda `pytest` nie wskazuje jednoznacznie katalogu z konfiguracją w `backend/pyproject.toml`;
- opis kontroli pre-commit nie odzwierciedla w pełni użycia Gitleaks, TruffleHog i skanu historii;
- `make security-all` ignoruje kody błędów poszczególnych narzędzi, więc nie może być traktowane jako jednoznaczna bramka jakości.

**Aktualizacja 2026-07-12:** wszystkie powyższe rozjazdy zostały skorygowane (licencja — patrz decyzja D7; pozostałe — patrz status zadań w etapie 5). Sekcję pozostawiono jako zapis ustaleń audytu.

### 4.4. Konfiguracja MCP jest specyficzna dla Claude

Plik `.mcp.json` nie jest docelową projektową konfiguracją MCP dla Codex. Brakuje odpowiadającej mu konfiguracji w `.codex/config.toml`.

### 4.5. Komendy Claude nie są workflow Codex

Pliki `.claude/commands/*.md` nie są automatycznie dostępne jako skille Codex. Masowa konwersja byłaby kosztowna w utrzymaniu i mogłaby niepotrzebnie zwiększyć liczbę podobnych workflow.

### 4.6. Konwencje zależne od konkretnego agenta

Następujące reguły nie powinny być bezpośrednio kopiowane do Codex:

- eksportowanie plików wyłącznie do `.claude/exports/`;
- wymuszanie autora commitów `Claude Code <noreply@anthropic.com>`.

## 5. Docelowa struktura

Proponowana struktura po wdrożeniu planu:

```text
AGENTS.md
CLAUDE.md
.codex/
  config.toml
.agents/
  skills/
    security-check/
      SKILL.md
    feed-review/
      SKILL.md
    bmad-code-review/
      SKILL.md
docs/
  agent/
    repository-map.md
    verification.md
    safety.md
backend/
  AGENTS.md
backend/database/
  AGENTS.md
backend/imports/
  AGENTS.md
infra/aws/
  AGENTS.md
web_interface_react/
  AGENTS.md
web_interface_app2/
  AGENTS.md
web_chrome_extension/
  AGENTS.md
```

Lista skilli jest przykładowa i wymaga osobnej decyzji.

## 6. Etapy implementacji

### Etap 0: prerekwizyty środowiska wykonawczego Codex (Windows) — UKOŃCZONY 2026-07-12

#### Kontekst

Żaden kontrakt dokumentacyjny nie zadziała, jeśli Codex nie może fizycznie czytać repozytorium. Audyt z 2026-07-12 wykazał twardy blocker: natywny sandbox Codex na Windows uruchamia komendy jako dedykowane konta lokalne (`CodexSandboxOffline`, `CodexSandboxOnline`), które nie mają dostępu NTFS do repozytorium położonego w profilu użytkownika (`C:\Users\<user>\git\...`). Skutek: `CreateProcessWithLogonW failed: 267`, reviewer nie widzi diffa i zwraca werdykt bez pokrycia (zaobserwowane przy pierwszym `/codex:review` w tym repozytorium). Problem zgłaszany także u innych użytkowników: [openai/codex#19599](https://github.com/openai/codex/issues/19599), [openai/codex#18620](https://github.com/openai/codex/issues/18620).

#### Zakres

Nadać kontom sandboxa minimalne uprawnienia odczytu:

1. Odczyt drzewa repozytoriów (dziedziczony):
   `icacls "C:\Users\<user>\git" /grant "CodexSandboxOffline:(OI)(CI)RX" "CodexSandboxOnline:(OI)(CI)RX"`
2. Przejście (traverse, bez listowania) przez katalog profilu:
   `icacls "C:\Users\<user>" /grant "CodexSandboxOffline:(X)" "CodexSandboxOnline:(X)"`

Uwagi operacyjne:

- Konto sandboxa nie ma przywileju „bypass traverse checking", więc krok 2 jest niezbędny — sam wpis na `git\` nie wystarcza (zweryfikowane empirycznie).
- Zmiana DACL na katalogu profilu wyzwala systemową repropagację dziedziczonych wpisów po całym poddrzewie (AppData itd.) — operacja trwa długo; uruchamiać w oknie terminala, które nie zostanie przerwane, i czekać na `Successfully processed 1 files`.
- W Git Bash wymagany prefiks `MSYS_NO_PATHCONV=1` (inaczej `/grant` jest zamieniany na ścieżkę).
- Cofnięcie: `icacls <ścieżka> /remove CodexSandboxOffline CodexSandboxOnline`.

Alternatywy, jeśli ACL-e okażą się niewystarczające: uruchamianie Codex w WSL (sandbox Landlock/seccomp zamiast kont Windows) albo świadoma rezygnacja z sandboxa (`--sandbox danger-full-access`) — do decyzji, ze świadomością obniżenia izolacji.

#### Kryteria akceptacji

- `codex sandbox cmd /c "git status"` uruchomione w katalogu repozytorium wykonuje się bez błędu 267 i bez przekierowania cwd do katalogu zastępczego (`C:\Users\CodexSandboxOffline\.codex\.sandbox\cwd\...`).
- `/codex:review` czyta diff repozytorium i zwraca werdykt oparty na kodzie (bez zastrzeżenia o niedostępnym workspace).

#### Status (2026-07-12)

- [x] Diagnoza (konta sandboxa, błąd 267, brak bypass-traverse)
- [x] Wpis `(OI)(CI)RX` na `C:\Users\ziutus\git` dla obu kont
- [x] Wpis traverse `(X)` na `C:\Users\ziutus` — założony (repropagacja DACL po profilu trwała ~50 min; obserwacja: po udrożnieniu traverse Codex sam nadał grupie `CodexSandboxUsers` prawo Modify na katalogu repozytorium — to jego własny mechanizm zarządzania dostępem workspace)
- [x] Weryfikacja `codex sandbox` w repozytorium — `git log` i `git status` działają, cwd nie jest przekierowywane (uwaga: sandboxowy PowerShell potrafi zostawić w cwd artefakt `Microsoft/Windows/PowerShell/ModuleAnalysisCache` — usuwać, nie commitować)
- [x] Ponowny `/codex:review` z werdyktem opartym na kodzie — reviewer przeczytał diff working tree i zwrócił merytoryczne znalezisko (P2 dot. plików licencji w artefaktach pakietów). **Etap 0 ukończony 2026-07-12.**

### Etap 1: główny `AGENTS.md`

#### Zakres

Utworzyć krótki główny kontrakt Codex zawierający:

- mapę repozytorium;
- routing do dokumentacji komponentów;
- podstawowe komendy;
- zasady doboru i raportowania testów;
- zasady bezpieczeństwa sekretów;
- ograniczenia dotyczące deployów, migracji, AWS i produkcji;
- regułę zachowania istniejących zmian użytkownika;
- krytyczną instrukcję Windows/WSL dla `.venv_wsl`;
- oczekiwany sposób raportowania zakończonego zadania.

#### Założenia redakcyjne

- Docelowo około 100–150 linii.
- Instrukcje operacyjne, bez szczegółowych inwentarzy architektury.
- Linki do źródeł szczegółowych zamiast ich kopiowania.
- Reguły krytyczne zapisane bezpośrednio, nawet jeśli występują również w dokumentacji wspólnej.

#### Kryteria akceptacji

- Codex może ustalić sposób instalacji, zmiany i walidacji bez czytania całego `CLAUDE.md`.
- Każda operacja wysokiego ryzyka ma jasno określoną granicę autoryzacji.
- Plik nie zawiera szybko dezaktualizujących się liczników endpointów, tabel lub testów.

### Etap 2: lokalne pliki `AGENTS.md`

#### Zakres początkowy

Utworzyć instrukcje dla obszarów o odmiennych technologiach lub ryzyku:

1. `backend/AGENTS.md`;
2. `backend/database/AGENTS.md`;
3. `backend/imports/AGENTS.md`;
4. `infra/aws/AGENTS.md`;
5. `web_interface_react/AGENTS.md`;
6. `web_interface_app2/AGENTS.md`;
7. `web_chrome_extension/AGENTS.md`.

#### Zasada zawartości

Każdy plik lokalny powinien odpowiadać na cztery pytania:

1. Jakie pliki i dokumenty są źródłem prawdy?
2. Jakie konwencje obowiązują w tym obszarze?
3. Jak zweryfikować zmianę?
4. Jakich operacji nie wykonywać bez wyraźnej zgody?

#### Kryteria akceptacji

- Instrukcje lokalne nie powtarzają całej dokumentacji komponentu.
- Nie są sprzeczne z głównym `AGENTS.md`.
- Zawierają tylko zasady odnoszące się do danego drzewa katalogów.

### Etap 3: wspólna dokumentacja agentów

#### Zakres

Utworzyć:

- `docs/agent/repository-map.md` — stabilna mapa komponentów i źródeł prawdy;
- `docs/agent/verification.md` — macierz walidacji zależna od zakresu zmian;
- `docs/agent/safety.md` — sekrety, wdrożenia, migracje, dane produkcyjne i operacje zewnętrzne.

#### Zasada źródła prawdy

- `AGENTS.md` i `CLAUDE.md` pozostają krótkimi kontraktami dla poszczególnych agentów.
- Szczegóły wspólne znajdują się w `docs/agent/`.
- Wersje technologii powinny pochodzić z plików wykonywalnej konfiguracji, takich jak `pyproject.toml` i `package.json`.

#### Kryteria akceptacji

- Claude Code i Codex odwołują się do tych samych dokumentów wspólnych.
- Aktualizacja komendy walidacyjnej nie wymaga edycji wielu instrukcji agentów.

### Etap 4: macierz walidacji

W `docs/agent/verification.md` zapisać co najmniej następujące przypadki:

| Zakres zmiany | Minimalna walidacja | Dodatkowa walidacja |
|---|---|---|
| Czysta logika Python | test dotyczący zmiany, Ruff | szerszy zestaw unit |
| Backend API | test endpointu, Ruff | pełne unit lub integration |
| ORM lub schemat bazy | unit modeli | integration z PostgreSQL |
| Główny frontend | `npm test`, `npm run build` | test przepływu w przeglądarce |
| App2 | `npm run lint`, `npm run build` | test manualny zmienionej funkcji |
| Landing page | `npm run build` | kontrola statycznego eksportu |
| Rozszerzenie Chrome | kontrola składni i manifestu | test po załadowaniu rozszerzenia |
| CloudFormation | walidacja lokalna | change set, wyłącznie na polecenie |
| Zależności Python | `uv lock`, testy Windows | synchronizacja i kontrola WSL |
| Wspólne typy TypeScript | build wszystkich konsumentów | testy konsumentów |

Macierz powinna rozróżniać:

- walidację możliwą offline;
- walidację wymagającą sieci;
- walidację wymagającą bazy;
- operacje wymagające danych uwierzytelniających;
- operacje zmieniające stan zewnętrzny.

### Etap 5: korekta niespójności dokumentacji

#### Zadania

1. ~~Ustalić i ujednolicić deklarację licencji.~~ **Wykonane 2026-07-12** — patrz decyzja [D7](#d7-źródło-prawdy-dla-licencji--rozstrzygnięte-i-wdrożone-2026-07-12).
2. ~~Zaktualizować opis landing page na podstawie `package.json`.~~ **Wykonane 2026-07-12** — `CLAUDE.md` opisuje Next.js 15 + React 19 i odsyła po dokładne wersje do `web_landing_page/package.json`.
3. ~~Usunąć z głównego kontraktu ręcznie utrzymywaną liczbę tabel.~~ **Wykonane 2026-07-12** — sekcja Database opisuje dwie tabele rdzeniowe bez licznika kolumn i odsyła do `backend/database/CLAUDE.md` jako inwentarza oraz do `backend/alembic/` jako źródła migracji.
4. ~~Ujednolicić zalecaną komendę uruchamiania testów backendu.~~ **Wykonane 2026-07-12** — `CLAUDE.md` zaleca uruchamianie z `backend/` z `PYTHONPATH=.` i venv projektu (gołe `pytest` z korzenia usunięte).
5. ~~Zaktualizować opis pre-commit i skanowania sekretów.~~ **Wykonane 2026-07-12** — opis obejmuje Gitleaks + TruffleHog na zmianach oraz pre-push skan historii niewypchniętych commitów.
6. ~~Wyraźnie opisać, że `make security-all` agreguje wyniki, ale nie stanowi bramki kończącej się błędem.~~ **Wykonane 2026-07-12** — dopisane wprost przy komendzie (prefiks `-` w Makefile ignoruje kody wyjścia narzędzi).
7. Sprawdzić pozostałe wersje, liczniki i informacje oznaczone datami.

#### Opcjonalna automatyzacja

Rozważyć skrypt lub test dokumentacji sprawdzający:

- zgodność wersji projektu między wskazanymi plikami;
- istnienie komend wymienionych w dokumentacji;
- istnienie linkowanych plików;
- zgodność wersji frameworków z `package.json`;
- brak niedozwolonych sekretów i rzeczywistych danych dostępowych w przykładach.

### Etap 6: projektowa konfiguracja Codex

#### Zakres

Utworzyć `.codex/config.toml` dla ustawień, które powinny być wspólne w tym repozytorium.

Do rozważenia:

- konfiguracja serwerów MCP;
- ustawienia sandboxa i zatwierdzania operacji;
- ustawienia specyficzne dla zaufanego repozytorium;
- ewentualne hooki kontrolne.

#### Zasady bezpieczeństwa

- Nie zapisywać tokenów, haseł ani kluczy w repozytorium.
- Preferować przekazywanie nazw zmiennych środowiskowych.
- Zachować tryb read-only dla MCP, które nie muszą wykonywać zapisów.
- Nie włączać domyślnie narzędzi modyfikujących AWS.
- Oddzielić ustawienia współdzielone od prywatnego profilu użytkownika.

#### Migracja MCP

Dla każdego wpisu z `.mcp.json` podjąć jedną z decyzji:

| MCP | Proponowana decyzja | Uwagi |
|---|---|---|
| AWS IaC | przenieść lub pozostawić w profilu | zależy od częstotliwości użycia |
| CloudFormation | przenieść jako read-only | zachować argument `--readonly` |
| AWS API | przenieść jako read-only | zachować `READ_OPERATIONS_ONLY=true` |
| GitGuardian | decyzja osobna | wymaga sieci i uruchomienia przez `uvx` |
| WordPress.com | nie przenosić domyślnie | obecnie wyłączony |

#### Kryteria akceptacji

- `codex mcp list` pokazuje oczekiwane serwery.
- Start Codex nie wymaga sekretów zapisanych w repo.
- Narzędzia AWS nie mogą przypadkowo wykonywać zapisów.

### Etap 7: skille dla powtarzalnych workflow

#### Podejście

Nie konwertować automatycznie wszystkich `.claude/commands`. Najpierw zebrać informacje, które workflow są faktycznie używane.

#### Kandydaci do pierwszej iteracji

- `security-check`;
- `feed-review`;
- `bmad-code-review`;
- opcjonalnie `obsidian-note`;
- opcjonalnie jeden skrócony workflow implementacyjny BMAD.

#### Kryteria wyboru

Workflow powinien zostać skillem, jeśli:

- jest używany cyklicznie;
- ma stabilną kolejność kroków;
- wymaga konkretnych plików referencyjnych lub skryptów;
- ręczne promptowanie często prowadzi do pominięcia kroku;
- jego zakres można jasno odróżnić od innych skilli.

#### Kryteria akceptacji

- Każdy skill ma jednoznaczną nazwę i opis wyzwalania.
- Instrukcja wskazuje, kiedy skill nie powinien być używany.
- Skill nie kopiuje niepotrzebnie całego workflow BMAD.
- Skryptowe kroki są deterministyczne i możliwe do osobnego uruchomienia.

### Etap 8: neutralne konwencje agentów

#### Eksporty

Zastąpić `.claude/exports/` neutralną lokalizacją, np.:

- `tmp/agent-exports/`; albo
- `.agents/exports/`.

Wybrana lokalizacja powinna być ignorowana przez Git, chyba że użytkownik wyraźnie chce wersjonować rezultat.

#### Autorstwo commitów

Rozstrzygnięte w decyzji [D4](#d4-polityka-commitów--rozstrzygnięte-2026-07-12): każdy agent zachowuje osobną politykę wyłącznie w swoim pliku platformowym (dawny wariant 3). Reguła autora `Claude Code <noreply@anthropic.com>` pozostaje w `CLAUDE.md`; do reguł wspólnych (`docs/agent/`) i do `AGENTS.md` nie wchodzi.

### Etap 9: walidacja działania agentów

Po wdrożeniu przeprowadzić kontrolowane zadania próbne:

1. Niewielka zmiana czystej funkcji backendu.
2. Zmiana endpointu Flask wymagająca testu.
3. Zmiana typu współdzielonego wpływająca na dwa frontendy.
4. Review szablonu CloudFormation bez wdrażania.
5. Zmiana zależności Python z kontrolą Windows/WSL.
6. Zadanie wykorzystujące jeden nowy skill.

Dla każdego zadania ocenić:

- czy agent przeczytał właściwe instrukcje;
- czy wybrał odpowiednie testy;
- czy nie wykonał operacji poza zakresem;
- czy poprawnie zgłosił niewykonane kontrole;
- ile niepotrzebnych plików dokumentacji otworzył;
- czy wynik wymagał korekty użytkownika.

## 7. Decyzje wymagane przed implementacją

### D1. Model współdzielenia dokumentacji

- **Wariant A — rekomendowany:** krótkie `AGENTS.md` i `CLAUDE.md` plus wspólne `docs/agent/`.
- Wariant B: niezależne, kompletne instrukcje dla każdego agenta.
- Wariant C: `AGENTS.md` będący prawie pełną kopią `CLAUDE.md`.

### D2. Zakres lokalnych `AGENTS.md`

- **Wariant A — rekomendowany:** tylko obszary o różnych technologiach lub poziomie ryzyka.
- Wariant B: odpowiednik każdego istniejącego lokalnego `CLAUDE.md`.

### D3. Lokalizacja eksportów agentów

- `tmp/agent-exports/`;
- `.agents/exports/`;
- pozostawienie osobnych lokalizacji dla Claude i Codex.

### D4. Polityka commitów — ROZSTRZYGNIĘTE (2026-07-12)

- Wariant A: bez specjalnego autora; commit wyłącznie na polecenie.
- Wariant B: neutralny autor automatyzacji.
- Wariant C: osobny autor dla każdego agenta.

**Decyzja: zachować obecną praktykę (wariant C).** Dotychczasowy przepływ odpowiada użytkownikowi: agent commituje ukończoną pracę na feature branchu (nigdy na `main`), z autorem zdefiniowanym w swoim pliku platformowym — dla Claude Code jest to `--author="Claude Code <noreply@anthropic.com>"` zapisane w `CLAUDE.md`. Konsekwencje: reguła autorstwa pozostaje w `CLAUDE.md` i **nie wchodzi** do wspólnej warstwy `docs/agent/` ani do `AGENTS.md`; polityka commitów Codex zostanie zdefiniowana osobno w `AGENTS.md` przy etapie 1 (domyślnie: commit tylko na polecenie, dopóki Codex nie zostanie sprawdzony w zadaniach próbnych z etapu 9).

### D5. Zakres projektowego MCP

- **Wariant A:** tylko bezpieczne MCP read-only w repo, pozostałe w profilu użytkownika.
- Wariant B: wszystkie obecnie aktywne MCP w `.codex/config.toml`.
- Wariant C: cała konfiguracja MCP wyłącznie w profilu użytkownika.

### D6. Pierwsza lista skilli

Wybrać maksymalnie 3–5 workflow do pierwszej iteracji na podstawie rzeczywistego użycia.

### D7. Źródło prawdy dla licencji — ROZSTRZYGNIĘTE I WDROŻONE (2026-07-12)

**Decyzja: źródłem prawdy jest plik `LICENSE` w korzeniu repozytorium (BSL 1.1, konwersja do Apache 2.0 w 2030-03-12).** Deklaracje MIT w pakietach były przeoczeniem z szablonu — audyt wykazał, że problem dotyczył nie tylko backendu, lecz **czterech** plików `pyproject.toml`: `backend/`, `ner_service/`, `slack_bot/` i `shared_python/unified-config-loader/`. Wszystkie cztery poprawiono docelowo na `license = { file = "LICENSE" }` z kopią pliku `LICENSE` w katalogu każdego pakietu — samo `text = "BUSL-1.1"` (pierwsza wersja poprawki) nie dołączało do artefaktów budowanych niezależnie (wheel/sdist) treści licencji z Additional Use Grant i Change Date, co wychwycił pierwszy działający `/codex:review` (znalezisko P2). Zweryfikowano buildem: wheel zawiera `dist-info/licenses/LICENSE` z pełną treścią i metadaną `License: Business Source License 1.1`. Frontendy (`package.json`) nie deklarują licencji, więc nie wymagały zmian. Tym samym zadanie 1 z etapu 5 jest wykonane; kontrola zgodności licencji to dobry kandydat do automatyzacji opisanej w etapie 5.

## 8. Ryzyka i sposoby ograniczenia

| Ryzyko | Skutek | Ograniczenie |
|---|---|---|
| Duplikacja instrukcji | rozjazdy między agentami | wspólne `docs/agent/` i krótkie pliki platformowe |
| Zbyt długi `AGENTS.md` | gorszy routing i większy kontekst | limit zakresu, linkowanie szczegółów |
| Zbyt wiele lokalnych plików | koszt utrzymania | tworzyć tylko przy realnie odmiennych zasadach |
| Zbyt wiele skilli | niejednoznaczne wyzwalanie | mała pierwsza iteracja i precyzyjne opisy |
| MCP wymagające sieci lub sekretów | błędy startu, ryzyko danych | profil użytkownika i zmienne środowiskowe |
| Nieaktualne wersje w dokumentacji | błędne decyzje agenta | konfiguracja wykonywalna jako źródło prawdy |
| Fałszywie pozytywna walidacja bezpieczeństwa | niewykryte problemy | raportowanie wyników każdego narzędzia osobno |
| Operacje chmurowe bez zgody | zmiana stanu lub koszty | jawna granica autoryzacji w instrukcjach |

## 9. Proponowana kolejność realizacji

0. Dokończyć etap 0 (dostęp sandboxa Codex do repozytorium na Windows) — bez niego walidacja pozostałych etapów jest niemożliwa.
1. Podjąć decyzje D1–D7.
2. Skorygować najważniejsze rozjazdy faktów.
3. Utworzyć `docs/agent/verification.md` i `docs/agent/safety.md`.
4. Utworzyć główny `AGENTS.md`.
5. Utworzyć minimalny zestaw lokalnych `AGENTS.md`.
6. Skrócić i uporządkować `CLAUDE.md`, zachowując obsługę Claude Code.
7. Dodać `.codex/config.toml` po ustaleniu zakresu MCP.
8. Utworzyć pierwsze 3–5 skilli.
9. Przeprowadzić zadania próbne i zebrać korekty.
10. Dodać lekką automatyczną kontrolę dryfu dokumentacji.

## 10. Definicja ukończenia

Adaptację można uznać za ukończoną, gdy:

- sandbox Codex ma dostęp do repozytorium na maszynie deweloperskiej (etap 0), a `/codex:review` zwraca werdykt oparty na kodzie;
- Codex ładuje główny i lokalne kontrakty repozytorium;
- Claude Code nadal otrzymuje poprawne instrukcje;
- obaj agenci korzystają z tej samej macierzy walidacji i zasad bezpieczeństwa;
- komendy w dokumentacji odpowiadają konfiguracji projektu;
- konfiguracja Codex nie zawiera sekretów;
- operacje AWS i wdrożenia wymagają jawnej autoryzacji;
- wybrane skille działają w kontrolowanych zadaniach próbnych;
- nie występują znane sprzeczności dotyczące licencji, wersji technologii i struktury danych;
- użytkownik zaakceptował wynik zadań próbnych.

## 11. Sugerowany zakres pierwszego wdrożenia

Najmniejsza iteracja zapewniająca wyraźną poprawę jakości:

1. `docs/agent/verification.md`;
2. `docs/agent/safety.md`;
3. główny `AGENTS.md`;
4. `backend/AGENTS.md`;
5. `infra/aws/AGENTS.md`;
6. `web_interface_react/AGENTS.md`;
7. korekta wykrytych rozjazdów dokumentacji.

Konfigurację MCP i skille można wdrożyć w drugiej iteracji po sprawdzeniu, jak Codex działa z samą poprawioną warstwą instrukcji.
