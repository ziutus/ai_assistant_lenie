# Gotowość bezpieczeństwa: sieć firmowa i chmura

Status: wymagania do weryfikacji przed przyszłym wdrożeniem, 2026-09-06.
To nie jest decyzja o migracji, potwierdzenie bezpieczeństwa obecnego NAS-a ani
polecenie wdrażania infrastruktury chmurowej na zapas.

## Kiedy stosować

Checklistę stosujemy przed udostępnieniem aplikacji w sieci firmowej, przekazaniem
jej utrzymania innemu operatorowi lub wdrożeniem chmurowym. Wewnętrzna instalacja
jednej organizacji nie wymaga automatycznie wielodostępnego SaaS, ale nie dziedziczy
zaufania do wszystkich urządzeń z profilu jednego dewelopera.

[Profil lokalny](local-development-security.md) opisuje uproszczenia, które trzeba
ponownie ocenić. Docker Compose z NAS-a nie jest gotowym wzorcem produkcyjnym.
Przeniesienie kontenera lub sekretu do Kubernetes samo nie zmienia logiki aplikacji
ani jakości zapisanych poświadczeń.

## Minimum dla instalacji firmowej i prywatnej chmury

Każdy punkt wymaga dowodu: konfiguracji, wyniku testu lub odnośnika do procedury.
W karcie konkretnego wdrożenia należy zapisać status `spełnione`, `niespełnione`
albo uzasadnione `nie dotyczy`, osobę odpowiedzialną, datę i dowód. Poniższa lista
nie jest jeszcze odhaczona dla żadnego środowiska.

| Obszar | Warunek gotowości | Jak zweryfikować | Odpowiedzialność |
|---|---|---|---|
| Znane błędy kodu | Zamknięte cztery problemy z [przeglądu lokalnego](local-development-security.md): uprawnienia usuwania, SSRF, preflight i cache. | Testy regresyjne, w tym odmowa usuwania dla `read_only`, brak skutków `GET`/`HEAD`, redirect do celu wewnętrznego i limit cache. | Zespół aplikacji. |
| Model uprawnień | Jawnie określone role, wspólne/prywatne dane i uprawnienia operacyjne. Brak domyślnego prawa administracji dla użytkownika. | Macierz ról i testy API dla operacji dozwolonych oraz zabronionych; sprawdzona dezaktywacja kluczy we wszystkich replikach. | Właściciel produktu i zespół aplikacji. |
| Registry | TLS, uwierzytelnianie oraz ograniczenie publikowania/usuwania obrazów do procesu wydawniczego. Wewnętrzne registry jest dozwolone. | Próba anonimowego i nieuprawnionego push/delete odrzucona; środowisko uruchomieniowe ma tylko potrzebne prawa pobierania. | Operator / zespół wdrożeń; dostawca utrzymuje usługę w zakresie umowy. |
| Wersje i zależności | Wdrożenia identyfikowane digestem i commitem; ocena wyników skanowania zależności/obrazów; zachowana wersja do rollbacku. | Odtworzenie dokładnie tej samej wersji i próba wycofania na środowisku testowym. | Zespół wdrożeń i aplikacji. |
| Baza i sekrety | Brak fallbacku `postgres` i innych przykładowych haseł. Sekrety poza repozytorium; konto aplikacji z minimalnymi uprawnieniami, odrębne od administracji/migracji. | Start bez wymaganej konfiguracji odrzucony; sprawdzone uprawnienia i procedura rotacji istniejących poświadczeń. | Operator bazy i aplikacji. |
| Sieć i transport | Dostęp do API zgodny z grupą odbiorców, chroniony transport; baza, storage i administracja dostępne tylko dla wskazanych klientów. | Próby połączeń z hosta użytkownika, administracyjnego i nieuprawnionego; przegląd portów, zapory, ingressu i certyfikatów. | Operator infrastruktury. |
| Ruch wychodzący | Pobieranie obcych treści nie daje dostępu do paneli, usług wewnętrznych ani metadanych infrastruktury. Wymagane połączenia opisane jawnie. | Kontrolowane testy adresów i przekierowań oraz reguł wyjściowych; w Kubernetes sprawdzenie, że polityki są faktycznie egzekwowane. | Aplikacja i operator sieci. |
| Kontenery i zasoby | Minimalne uprawnienia procesu, uzasadnione mounty, brak zbędnego dostępu do hosta/Docker socket; limity zasobów i rozmiarów przetwarzanych danych. | Przegląd manifestów i test zachowania przy przekroczeniu limitów. | Operator i aplikacja. |
| Audyt i nadużycia | Rejestrowanie operacji administracyjnych i błędów autoryzacji bez sekretów; określona retencja, alerty i zasady limitowania ruchu. | Przykładowe zdarzenie da się przypisać do tożsamości; sprawdzony alert i brak kluczy w logach. | Operator i aplikacja. |
| Backup i odzyskiwanie | Kopie bazy i plików, oddzielne poświadczenia, określony dopuszczalny czas/przedział utraty danych oraz procedura odzyskania. | Udokumentowana próba odtworzenia, nie tylko potwierdzenie utworzenia kopii. | Właściciel danych i operator. |
| Dane i usługi zewnętrzne | Wiadomo, jakie dane trafiają do LLM, transkrypcji i innych dostawców, kto zatwierdza ten przepływ i jak długo dane są przechowywane. | Przegląd konfiguracji integracji oraz uzgodnienie z właścicielem danych organizacji. | Właściciel danych i aplikacja. |

## Dodatkowe wymagania zależne od ekspozycji

- **Publiczne API:** przed publikacją ustalić i przetestować ochronę przed masowymi
  próbami dostępu, limity żądań i kosztownych operacji, monitoring oraz reakcję na
  incydent. Wyjątek household dotyczący odłożenia rate limitingu nie przechodzi tu
  automatycznie.
- **Wiele niezależnych klientów lub prywatne biblioteki:** potrzebna osobna decyzja
  o izolacji danych, uprawnieniach i budżetach. Patrz
  [eksperyment wielodostępny](../deployment/commercial-multi-tenant-scaling-experiment.md).
- **Kubernetes:** określić uprawnienia kont serwisowych, dostęp do sekretów,
  izolację sieci i model aktualizacji klastra. Sam namespace nie jest dowodem
  spełnienia tych wymagań.

## Co może zapewnić dostawca, a co pozostaje po naszej stronie

Registry dostawcy może zastąpić lokalny serwer HTTP. Nadal wybieramy widoczność
repozytorium, nadajemy uprawnienia i wskazujemy wdrażany digest. Szybkość kolejnej
instalacji nie zastępuje kontroli pochodzenia i publikacji obrazów.

Zarządzana baza zastępuje lokalny kontener i jego inicjalizację, jeśli nie
przeniesiemy tej konfiguracji dalej. Fallback `${NAS_DB_PASSWORD:-postgres}` jest
zapisem naszego Compose, nie wymaganiem środowiska chmurowego. Dla wybranej usługi
trzeba zweryfikować sposób tworzenia poświadczeń/tożsamości i rotacji. Własny
PostgreSQL w Kubernetes może odziedziczyć słabe hasło z manifestu lub chartu;
umieszczenie go w Secret nie rozwiązuje problemu.

Dostawca nie naprawia uprawnień endpointów, obsługi `OPTIONS`, pobierania feedów
ani cache aplikacji. Zakres jego odpowiedzialności za backup, aktualizacje i
transport trzeba potwierdzić dla konkretnej usługi i konfiguracji.

## Decyzje i powiązana dokumentacja

Przy rzeczywistym wyborze środowiska powstaje ADR opisujący model zaufania,
ekspozycję, usługi zarządzane i odpowiedzialności. Nie tworzymy osobnego ADR dla
każdego punktu checklisty. Wyjątki wymagają wskazania ryzyka, właściciela,
zabezpieczeń zastępczych oraz terminu ponownej oceny.

- [Mapa wdrożeń](../deployment/README.md) i [eksperyment AWS/Google Cloud](../deployment/hyperscalers/aws-gcloud-experiment.md): migracja nadal jest osobnym, przyszłym wyborem.
- [On-premise](../deployment/onprem/enterprise-onprem-experiment.md): wdrożenie organizacji nie musi być SaaS.
- [ADR-002](../adr/adr-002-api-gateway-security-boundary.md): historyczna granica API Gateway, status dormant; nie dowodzi zabezpieczenia obecnego Flask API.
- [ADR-016](../adr/adr-016-cloudformation-vs-cdk.md): uwzględnić przy wyborze IaC dla AWS.
- [Secrets Management](secrets-management.md) i [skanowanie zależności](dependency-supply-chain-scanning.md): istniejące instrukcje wykonawcze.
