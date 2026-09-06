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

## Błędy aplikacji nie są lokalnymi wyjątkami

Przegląd kodu `a80f11bb9874495e1e770ef76f96f14191c5f0b9` wskazał poniższe
problemy. Ten zapis nie oznacza ich naprawienia; zamknięcie wymaga wskazania zmiany
i wyniku weryfikacji.

| Problem | Oczekiwane zachowanie po poprawce | Status |
|---|---|---|
| Usuwanie dokumentu przez `GET /website_delete`, dostępne dla `read_only` | `GET` i `HEAD` nie usuwają danych; operacja usuwania wymaga prawa zapisu. | Naprawione — endpoint zmieniony na `DELETE` (gate metod blokuje `read_only`). |
| Feed pobierany bez ochrony SSRF | Początkowy adres i przekierowania nie pozwalają dotrzeć do niedozwolonych celów wewnętrznych; połączenie używa zweryfikowanego celu. | Naprawione — `library/safe_http.py` (DNS rozwiązywany raz, socket przypięty do zweryfikowanego adresu, każde przekierowanie walidowane); wpięte też w pobieranie stron i linków trackingowych. |
| `OPTIONS /uploads` zwraca metadane bez klucza | Preflight nie wykonuje listowania ani nie ujawnia danych. | Naprawione — `OPTIONS` zwraca puste `204` przed dostępem do storage. |
| Nieograniczony cache błędnych kluczy API | Wygasłe wpisy są usuwane, a pamięć cache ma ograniczony rozmiar. | Naprawione — limit 10 000 wpisów, przy przepełnieniu usuwane wygasłe, potem najstarszy. |

Wszystkie cztery poprawki są na gałęzi `fix/security-4-issues`; opis zmian i wynik
weryfikacji: [security-4-fixes-verification.md](security-4-fixes-verification.md).

Zaufany operator nadal importuje obce treści. Przejęty feed może uruchomić SSRF,
a integracja z kluczem tylko do odczytu może przypadkowo wywołać usuwający endpoint.
Te poprawki nie wymagają przejścia na model SaaS ani zmiany istniejących ADR-ów.

## Przegląd wyjątków i dokumentacji

Przed rozszerzeniem dostępu właściciel instancji sprawdza każdy wyjątek i zapisuje
wynik w dokumentacji wdrożenia: datę, zakres dostępu, właściciela, zabezpieczenia
oraz termin lub zdarzenie kończące wyjątek. Niespełniony warunek nie jest domyślną
zgodą na dalsze stosowanie uproszczenia.

Ograniczenie pamięci cache jest poprawką implementacji. Rate limiting żądań jest
osobną decyzją: [plan household](../deployment/nas/multi-user-household.md)
świadomie go odkłada. Wprowadzenie go wymaga aktualizacji tego zakresu.
Nowy ADR jest właściwy dla wyboru docelowego środowiska, zmiany modelu zaufania
lub nowego komponentu architektury, nie dla każdej poprawki bezpieczeństwa.
