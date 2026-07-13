# Dostęp sandboxa Codex do repozytorium na Windows

## Cel i zakres

Procedura dotyczy natywnego Codex na Windows, gdy repozytorium znajduje się pod profilem użytkownika, a komendy wykonywane w sandboxie nie mogą odczytać właściwego katalogu roboczego.

Zmiana list ACL jest konfiguracją konkretnej maszyny. Nie należy wykonywać jej automatycznie podczas konfiguracji projektu ani zakładać, że jest potrzebna na każdym komputerze.

## Objawy

Możliwe objawy braku dostępu:

- `CreateProcessWithLogonW failed: 267`;
- `git status` lub `git log` nie widzi właściwego repozytorium;
- review nie może odczytać diffa;
- polecenia działają w katalogu zastępczym zamiast na plikach workspace;
- Codex może czytać pojedyncze pliki, ale nie może przejść przez katalogi nadrzędne.

Najpierw należy potwierdzić problem funkcjonalnie. Sama obecność wewnętrznej ścieżki sandboxa nie oznacza jeszcze, że workspace jest niedostępny.

## Model uprawnień

Natywny sandbox może wykonywać procesy z użyciem dedykowanych kont lokalnych:

- `CodexSandboxOffline`;
- `CodexSandboxOnline`.

Aby odczytać repozytorium znajdujące się pod `C:\Users\<user>`, konto potrzebuje prawa przejścia przez katalogi nadrzędne oraz praw odczytu i wykonania w katalogu repozytorium.

Należy przyznać możliwie najmniejszy zakres praw. Jeśli Codex ma pracować tylko z jednym repozytorium, preferowane jest nadanie praw do tego repozytorium zamiast do całego drzewa zawierającego inne projekty.

## Ostrzeżenie dotyczące zakresu

Polecenie skierowane na `C:\Users\<user>\git` udostępnia kontom sandboxa wszystkie repozytoria i inne pliki znajdujące się w tym drzewie. Przed wykonaniem polecenia należy sprawdzić jego zawartość i zdecydować, czy taki zakres jest zamierzony.

Zmiana ACL katalogu profilu może uruchomić przetwarzanie lub propagację wpisów w rozbudowanym poddrzewie. Nie należy przerywać operacji ani stosować dziedziczonych praw zapisu do całego profilu.

## Krok 1: diagnoza

W terminalu otwartym w repozytorium sprawdzić:

```powershell
git rev-parse --show-toplevel
git status --short
git log -1 --oneline
```

Następnie wykonać równoważne polecenie przez sandbox Codex, zgodnie ze składnią obsługiwaną przez zainstalowaną wersję klienta. Przykład:

```powershell
codex sandbox cmd /c "git rev-parse --show-toplevel && git status --short"
```

Jeżeli klient ma inną składnię, należy sprawdzić `codex sandbox --help`.

Przed zmianą ACL zapisać obecny stan:

```powershell
icacls "C:\Users\<user>"
icacls "C:\Users\<user>\git\<repozytorium>"
```

## Krok 2: minimalne prawa do jednego repozytorium

Preferowany wariant przyznaje dziedziczone prawa odczytu i wykonania tylko do wybranego repozytorium:

```powershell
icacls "C:\Users\<user>\git\<repozytorium>" /grant "CodexSandboxOffline:(OI)(CI)RX" "CodexSandboxOnline:(OI)(CI)RX"
```

Konta muszą również mieć możliwość przejścia przez katalog profilu:

```powershell
icacls "C:\Users\<user>" /grant "CodexSandboxOffline:(X)" "CodexSandboxOnline:(X)"
```

Jeżeli pośredni katalog `git` blokuje przejście, należy sprawdzić jego ACL i przyznać samo `(X)` temu katalogowi zamiast rozszerzać odczyt na całe drzewo:

```powershell
icacls "C:\Users\<user>\git" /grant "CodexSandboxOffline:(X)" "CodexSandboxOnline:(X)"
```

Nie należy przyznawać `F` (Full control) ani praw zapisu do całego profilu.

Ten krok ma zapewnić minimalny dostęp odczytu i przejścia przez katalogi. Jeżeli profil sandboxa Codex ma pozwalać na zapis w workspace, uprawnienia zapisu powinny wynikać z mechanizmu zarządzania workspace przez Codex lub z osobnej, świadomej decyzji dla konkretnego repozytorium. Nie należy rozwiązywać problemu zapisu przez rozszerzanie praw do całego profilu użytkownika.

## Wariant dla wielu repozytoriów

Jeżeli świadomie akceptowany jest odczyt całego drzewa repozytoriów:

```powershell
icacls "C:\Users\<user>\git" /grant "CodexSandboxOffline:(OI)(CI)RX" "CodexSandboxOnline:(OI)(CI)RX"
icacls "C:\Users\<user>" /grant "CodexSandboxOffline:(X)" "CodexSandboxOnline:(X)"
```

Ten wariant jest wygodniejszy, ale ma szerszy zakres dostępu.

## Git Bash

Git Bash może przekształcić argument `/grant` w ścieżkę. Aby temu zapobiec, należy wyłączyć konwersję ścieżek dla wywołania `icacls`:

```bash
MSYS_NO_PATHCONV=1 icacls "C:\Users\<user>\git\<repozytorium>" /grant "CodexSandboxOffline:(OI)(CI)RX" "CodexSandboxOnline:(OI)(CI)RX"
MSYS_NO_PATHCONV=1 icacls "C:\Users\<user>" /grant "CodexSandboxOffline:(X)" "CodexSandboxOnline:(X)"
```

## Weryfikacja

Po zmianie należy sprawdzić wynik ACL:

```powershell
icacls "C:\Users\<user>"
icacls "C:\Users\<user>\git\<repozytorium>"
```

Następnie zweryfikować działanie sandboxa. Kryteria są funkcjonalne:

- `git rev-parse --show-toplevel` wskazuje oczekiwane repozytorium;
- `git status` i `git log` działają;
- Codex czyta rzeczywisty diff working tree;
- zapis dozwolony przez profil sandboxa trafia do właściwego workspace;
- nie powstają nieoczekiwane pliki poza repozytorium;
- review opiera wynik na kodzie, a nie zgłasza braku dostępu do workspace.

Sandboxowy PowerShell może utworzyć artefakt `Microsoft/Windows/PowerShell/ModuleAnalysisCache`. Nie należy go commitować. Jeśli pojawia się cyklicznie, należy dodać odpowiednią regułę ignorowania lub skorygować lokalizację cache w konfiguracji środowiska.

## Cofnięcie zmian

Przed cofnięciem należy ponownie wyświetlić ACL i upewnić się, że usuwany wpis dotyczy właściwej ścieżki.

```powershell
icacls "C:\Users\<user>\git\<repozytorium>" /remove CodexSandboxOffline CodexSandboxOnline
icacls "C:\Users\<user>" /remove CodexSandboxOffline CodexSandboxOnline
```

Jeżeli prawa zostały nadane także na pośrednim katalogu `git`, należy usunąć wpis również tam:

```powershell
icacls "C:\Users\<user>\git" /remove CodexSandboxOffline CodexSandboxOnline
```

Usunięcie wpisu z katalogu profilu może wpłynąć na inne repozytoria korzystające z tych samych kont sandboxa. Po cofnięciu należy ponownie wykonać testy diagnostyczne.

## Alternatywy

Jeśli konfiguracja ACL jest niewłaściwa dla danej maszyny, można rozważyć:

- przeniesienie repozytorium poza chronione drzewo profilu;
- uruchamianie Codex w WSL;
- zmianę profilu uprawnień sandboxa zgodnie z polityką organizacji;
- pracę bez sandboxa wyłącznie jako świadomą decyzję, ponieważ obniża poziom izolacji.

Nie należy automatycznie przechodzić na pełny dostęp tylko dlatego, że pierwsza próba konfiguracji ACL nie zadziałała.

## Prawo zapisu dla jednego repozytorium

Jeżeli podjęto świadomą decyzję, że sandbox ma modyfikować pliki konkretnego repozytorium (np. Codex implementuje zmiany, a człowiek lub inny agent robi code review), należy nadać prawo Modify bezpośrednio kontom sandboxa:

```powershell
icacls "C:\Users\<user>\git\<repozytorium>" /grant "CodexSandboxOffline:(OI)(CI)M" "CodexSandboxOnline:(OI)(CI)M"
```

Uwaga: nadanie prawa Modify grupie `CodexSandboxUsers` NIE wystarcza — restricted token sandboxa nie honoruje uprawnień grupowych i zapis kończy się odmową dostępu. Prawa muszą być nadane bezpośrednio kontom. Weryfikacja funkcjonalna:

```powershell
codex sandbox cmd /c "echo test > C:\Users\<user>\git\<repozytorium>\.claude\exports\sandbox_write_test.txt"
```

## Historia dla tego repozytorium

W dniu 2026-07-12 problem został potwierdzony i rozwiązany na maszynie deweloperskiej. Po zmianie praw `git log`, `git status` oraz review diffa zaczęły działać dla właściwego repozytorium. Jest to stan lokalnej maszyny, a nie gwarantowany element konfiguracji repozytorium.

W dniu 2026-07-13 podjęto świadomą decyzję o nadaniu kontom sandboxa prawa zapisu (Modify) do tego repozytorium, aby Codex mógł implementować zmiany bezpośrednio (workflow: Codex koduje, Claude Code robi review). Test zapisu przez `codex sandbox` przeszedł po nadaniu praw bezpośrednio kontom (wpis grupy `CodexSandboxUsers` z prawem M istniał wcześniej, ale nie działał).
