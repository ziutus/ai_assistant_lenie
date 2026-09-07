# Bezpieczeństwo lokalnego środowiska dewelopera

Status: profil lokalnego wdrożenia i rejestr warunkowych uproszczeń, 2026-09-06.
Właściciel ryzyka: właściciel instancji / deweloper.

## Zakres i granica zaufania

Bieżący profil dotyczy własnego NAS-a w lokalnej sieci dewelopera, z jednym
operatorem, krótkim cyklem zmian i ręczną diagnostyką. NAS przechowuje rzeczywiste
dane: określenie „deweloperski” nie oznacza, że można je bezkosztowo utracić.
[Model household](../deployment/nas/multi-user-household.md) opisuje osobno
rozszerzenie dostępu na zaufanych domowników i gości.

Ten dokument nie potwierdza aktualnych reguł zapory, hasła działającej bazy ani
braku dostępu spoza LAN. Warunki poniżej trzeba sprawdzić na wdrożeniu. Sam adres
prywatny, jedna osoba korzystająca z aplikacji lub nazwa „private registry” nie
potwierdzają izolacji od innych urządzeń i procesów.

Profil przestaje wystarczać przy udostępnieniu usług w sieci firmowej, publicznym
ingressie, dostępie niezaufanych użytkowników lub przejęciu utrzymania przez inną
osobę. Nowy dostęp przez VPN również wymaga przeglądu tego, jakie usługi osiągają
klienci VPN. Obowiązuje wtedy [checklista gotowości produkcyjnej](production-readiness.md).

## Rejestr uproszczeń infrastrukturalnych

Uproszczenia są ograniczone do tego profilu. Nie są wzorcem konfiguracji produkcji
ani potwierdzeniem, że ich warunki są już spełnione.

| Uproszczenie | Uzasadnienie lokalne | Ryzyko i warunki dopuszczalności | Kiedy wycofać / co zastąpić |
|---|---|---|---|
| Registry na NAS, HTTP bez uwierzytelniania, z usuwaniem obrazów | Szybkie iteracje: build na PC, push i pull w LAN, bez eksportu archiwów, `scp` i `docker load`. | Dostęp do portu pozwala ingerować w obrazy. Warunkowo dopuszczalne tylko przy ograniczeniu dostępu do kontrolowanych hostów dewelopera i NAS-a; bez publikacji na Internet ani całą sieć gościnną/VPN. | Przed szerszym udostępnieniem: TLS, uwierzytelnianie, kontrola push/pull/delete. Registry może pozostać wewnętrzne albo zostać zastąpione usługą dostawcy. |
| Wdrażanie tagu `latest` | Prosty, ręczny cykl testowania pojedynczej instancji. | Tag nie identyfikuje niezmiennej wersji. Dopuszczalne przy akceptacji przerw oraz zachowaniu informacji o commitcie i digestach potrzebnych do odtworzenia wdrożenia. | Produkcja: wdrożenie po digestach, zapis wersji i przetestowany rollback. |
| Porty bazy, storage i paneli administracyjnych opublikowane na hoście | Bezpośrednia diagnostyka i lokalne skrypty. | Ominięcie granicy dostępu API. Dostęp powinien obejmować wyłącznie niezbędne hosty/operatora; zaufanie do użytkownika aplikacji nie daje automatycznie prawa do administracji bazą. | Sieć firmowa/chmura: prywatne połączenia usług i oddzielny, kontrolowany dostęp administracyjny. |
| Fallback `NAS_DB_PASSWORD` do `postgres` | Ułatwia start instalacji testowej bez przygotowania sekretu. | To zastana konfiguracja, nie potwierdzone hasło bazy ani automatycznie zaakceptowany wyjątek. Dopuszczalna wyłącznie dla izolowanej, jednorazowej bazy z danymi testowymi. NAS z rzeczywistymi danymi wymaga indywidualnego sekretu. | Usunąć fallback z konfiguracji przeznaczonej do trwałego wdrożenia; brak sekretu ma zatrzymać inicjalizację. Zmiana zmiennej nie jest dowodem zmiany hasła istniejącej bazy — potrzebna kontrolowana rotacja. |

Instrukcje techniczne i zastana konfiguracja znajdują się w
[NAS Deployment](../CICD/NAS_Deployment.md) oraz
[compose.nas.yaml](../../infra/docker/compose.nas.yaml).
Przechowywanie sekretów opisuje [Secrets Management](secrets-management.md).
Żadnych wartości rzeczywistych sekretów nie zapisujemy w dokumentacji.

## Inwarianty bezpieczeństwa aplikacji

Niezależnie od uproszczeń infrastrukturalnych z tabeli powyżej, aplikacja
egzekwuje w kodzie poniższe reguły. Nie są to warunkowe wyjątki: obowiązują
w każdym profilu wdrożenia i mają pokrycie testami regresyjnymi. Kontekst
zagrożenia jest realny — operator importuje obce treści, więc przejęty feed lub
link w newsletterze to wektor do wnętrza sieci, a integracja z kluczem tylko do
odczytu nie może przypadkiem wywołać operacji zmieniającej dane.

- **Klucz `read_only` nie modyfikuje danych.** Metody inne niż `GET`/`HEAD`/`OPTIONS`
  kończą się `403`. Usunięcie dokumentu wymaga metody `DELETE` i klucza z prawem
  zapisu (`user`/`service`); żadne `GET`/`HEAD` nie wywołuje skutków biznesowych.
- **Pobieranie zewnętrznych zasobów jest chronione przed SSRF.** Feedy (RSS/Atom/
  JSON/YouTube), strony do importu i linki trackingowe z newsletterów przechodzą
  przez wspólną walidację celu (`backend/library/safe_http.py`): nazwa hosta jest
  rozwiązywana raz, żądanie i każde przekierowanie mogą trafić wyłącznie na
  publiczny adres IP, a gniazdo jest przypięte do zweryfikowanego adresu. Loopback,
  sieci prywatne, link-local, CGNAT i endpointy metadanych infrastruktury są
  odrzucane. Konfiguracja feedu odrzuca też jawnie wewnętrzne adresy przy zapisie.
- **Preflight `OPTIONS` jest bez skutków ubocznych.** Nie wykonuje operacji storage
  ani nie zwraca danych — sama odpowiedź CORS.
- **Cache uwierzytelniania jest ograniczony.** Liczba wpisów ma górny limit, a
  wygasłe wpisy są odzyskiwane niezależnie od ponownego odpytania o ten sam klucz,
  więc rotacja nieznanych kluczy nie rośnie w pamięci ani nie generuje ruchu do bazy.

Limitowanie liczby żądań (rate limiting) jest świadomie odłożone — patrz
[plan household](../deployment/nas/multi-user-household.md). To znany,
zaakceptowany brak, a nie luka do cichego załatania; jego wprowadzenie wymaga
aktualizacji zakresu tego dokumentu.

Historia znalezisk (który model AI, kiedy, co wykrył) jest w osobnym
[dzienniku przeglądów AI](ai-review-findings-log.md) — celowym rejestrze
historycznym, nie opisie stanu bieżącego.

## Przegląd wyjątków i dokumentacji

Przed rozszerzeniem dostępu właściciel instancji sprawdza każdy wyjątek i zapisuje
wynik w dokumentacji wdrożenia: datę, zakres dostępu, właściciela, zabezpieczenia
oraz termin lub zdarzenie kończące wyjątek. Niespełniony warunek nie jest domyślną
zgodą na dalsze stosowanie uproszczenia.

Nowy ADR jest właściwy dla wyboru docelowego środowiska, zmiany modelu zaufania
lub nowego komponentu architektury, nie dla każdej poprawki bezpieczeństwa.
