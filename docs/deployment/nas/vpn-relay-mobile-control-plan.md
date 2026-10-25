# Start/stop VPN relay z telefonu z Androidem — plan wdrożenia

> Plan dokończenia części „Start/stop control” z
> [ADR-023](../../adr/adr-023-gcloud-vpn-relay-nas-access.md): publiczny, zabezpieczony
> kluczem endpoint HTTP dla Cloud Function `vpn-relay-control` oraz mała aplikacja na
> Androida, która go używa (status / start / stop relaya `lenie-vpn-relay`).
>
> **Status:** PLAN — nic z tego dokumentu nie jest jeszcze zaimplementowane.
> **Ostatnia aktualizacja:** 2026-10-22

## Punkt wyjścia (stan na 2026-10-22)

Szczegóły w [`infra/gcloud/terraform/CLAUDE.md`](../../../infra/gcloud/terraform/CLAUDE.md):

- VM `lenie-vpn-relay` (e2-micro, `europe-central2-a`) z serwerem OpenVPN, domyślnie
  **zatrzymana**. IP efemeryczne, hostname `vpn.gcloud.lenie-ai.eu` aktualizowany przez
  startup-script przy każdym starcie.
- Cloud Function `vpn-relay-control` (2nd gen, Python 3.12) obsługuje `start` / `stop` /
  `status`. **Nie ma publicznego endpointu.** Można ją wywołać tylko przez
  `gcloud functions call` (`make gcloud-vpn-start|stop|status`), czyli z komputera z
  zalogowanym `gcloud`.
- Telefon może się już łączyć z relayem jako zwykły klient OpenVPN (sekcja „VPN clients” w
  `infra/gcloud/terraform/CLAUDE.md`). Żeby jednak włączyć VM z telefonu, trzeba dziś wejść
  do Google Cloud Console (Compute Engine → `lenie-vpn-relay` → Start).

## Cel i zakres

**Cel:** włączyć relay, poczekać aż będzie gotowy, połączyć się VPN-em, a na koniec
wyłączyć VM, wszystko z telefonu, bez `gcloud` i bez Cloud Console.

**Poza zakresem:**
- frontend na Firebase Hosting z ADR-023 (aplikacja na Androida go zastępuje; można
  wrócić do niego później na tym samym API),
- publikacja w Google Play (wystarczy sideload APK dla jednej osoby lub kilku domowników),
- zmiany samej VM-ki i serwera OpenVPN (patrz „Ryzyko: wymuszone odtworzenie VM”).

## Decyzje

### Uwierzytelnianie: API Gateway + klucz API (zgodnie z ADR-023)

Zostajemy przy wzorcu z ADR-023, czyli lustrzanym odbiciu usuniętego AWS-owego
`ec2-manager`: **Google Cloud API Gateway** z kluczem API w nagłówku, a za nim istniejąca
funkcja bez publicznego invokera. Gateway woła funkcję z własnym kontem serwisowym, które ma
`roles/run.invoker` tylko na tej jednej usłudze. Limity i blokowanie klucza dostajemy
bez pisania kodu.

**Model zagrożeń:** wyciek klucza pozwala tylko na start/stop/status jednej VM-ki. Nie daje
dostępu do sieci NAS-a, bo ten nadal wymaga certyfikatu z profilu `.ovpn`. Najgorsze
możliwe skutki to:
- koszt pozostawionej włączonej VM (e2-micro, rząd groszy za godzinę),
- przerwanie tunelu przez złośliwy `stop`.

Oba ogranicza limit zapytań w API Gateway i możliwość szybkiej rotacji klucza. To ryzyko
uważamy za akceptowalne.

**Fallback**, gdyby API Gateway okazał się niepraktyczny (patrz „Do weryfikacji”): funkcja z
publicznym invokerem, która sama porównuje nagłówek `x-api-key` z sekretem w Secret Manager
(`hmac.compare_digest`). ADR-023 świadomie odrzucił ten wariant na rzecz parytetu z AWS.
Kontrakt HTTP poniżej jest jednak taki sam w obu wariantach, więc aplikacji na Androida ta
zmiana nie dotyczy.

### Aplikacja: natywna Kotlin + Jetpack Compose, sideload

Natywna aplikacja zamiast PWA, z dwóch powodów:
- kafelek w Szybkich ustawieniach (Quick Settings tile) i powiadomienia są realnie
  wygodniejsze niż strona w przeglądarce,
- przez API klienta OpenVPN for Android da się od razu połączyć VPN po starcie relaya.

**Szybka ścieżka bez kodu:** zaraz po Etapie 2, jeszcze przed aplikacją, można użyć
gotowej aplikacji typu *HTTP Shortcuts* (skróty na ekranie głównym z nagłówkiem
`x-api-key`). Własna aplikacja dokłada stan VM, czekanie na gotowość, kafelek i
przypomnienia.

## Kontrakt HTTP

Bazowy URL to domyślny hostname gatewaya (`https://<gateway>-<hash>.<region>.gateway.dev`).
API Gateway nie obsługuje natywnie własnych domen bez Load Balancera, a ten kosztuje około
$18-25 miesięcznie, więc własna domena odpada (ten sam powód co w ADR-023).

| Metoda | Ścieżka | Działanie |
|---|---|---|
| `GET` | `/status` | stan VM |
| `POST` | `/start` | start VM (asynchroniczny, nie czeka na `RUNNING`) |
| `POST` | `/stop` | stop VM (asynchroniczny) |

Każde zapytanie wymaga nagłówka `x-api-key`. Odpowiedź (JSON, także dla `start`/`stop`)
wygląda tak:

```json
{
  "action": "status",
  "status": "RUNNING",
  "external_ip": "34.158.231.226",
  "hostname": "vpn.gcloud.lenie-ai.eu"
}
```

- `status` to surowy status GCE: `PROVISIONING`, `STAGING`, `RUNNING`, `STOPPING`,
  `TERMINATED` (= zatrzymana) i inne. `external_ip` ma wartość `null`, gdy VM nie działa.
- Gdy VM już działa, `start` jest no-opem i zwraca 200 z aktualnym stanem. Tak samo
  zachowuje się `stop` na zatrzymanej VM.
- Błędy: 401/403 zwraca gateway (brak lub zły klucz), 429 (limit), 400 (nieznana akcja),
  500 (błąd Compute API; treść w polu `error`).

## Etapy

### Etap 1 — Cloud Function: JSON, akcja ze ścieżki, testy

Plik: `infra/gcloud/functions/vpn-relay-control/main.py`.

1. Akcja odczytywana kolejno ze **ścieżki** (`/start`, `/stop`, `/status`, potrzebne przy
   `APPEND_PATH_TO_ADDRESS` w gatewayu), z `?action=` i z body. Ścieżka `/` z body
   `{"action": ...}` dalej działa, więc `make gcloud-vpn-*` się nie psuje.
2. Odpowiedź w JSON według kontraktu wyżej. `external_ip` pochodzi z
   `instance.network_interfaces[0].access_configs[0].nat_ip`, a `hostname` ze zmiennej
   środowiskowej `VPN_HOSTNAME` ustawianej w `function.tf`.
3. `start`/`stop` są idempotentne: najpierw `get`, a akcję wywołujemy tylko wtedy, gdy ma
   sens. Nie czekamy na zakończenie operacji, bo aplikacja sama odpytuje `/status`.
4. Usunąć `Access-Control-Allow-Credentials: true`. W połączeniu z `Allow-Origin: *` to
   niepoprawna konfiguracja CORS, a natywna aplikacja i tak nie używa CORS.
5. Testy jednostkowe z zamockowanym `compute_v1.InstancesClient` w
   `infra/gcloud/functions/vpn-relay-control/tests/` (pytest; dev-zależności w osobnym
   `requirements-dev.txt`, żeby nie trafiały do builda funkcji).

**Weryfikacja:** testy przechodzą; po `terraform apply` `make gcloud-vpn-status` zwraca
JSON.

### Etap 2 — Terraform: API Gateway, klucz API, konto gatewaya

Nowy plik `infra/gcloud/terraform/api-gateway.tf` oraz szablon
`infra/gcloud/terraform/data/vpn-relay-api.yaml.tftpl` (OpenAPI 2.0, bo tylko ten format
obsługuje API Gateway).

1. Provider `google-beta` w `main.tf`, jeśli zasoby `google_api_gateway_*` nadal są
   tylko tam (do weryfikacji).
2. Włączenie usług `apigateway.googleapis.com`, `servicemanagement.googleapis.com`,
   `servicecontrol.googleapis.com` i `apikeys.googleapis.com`
   (`google_project_service`, `disable_on_destroy = false`, jak w `function.tf`).
3. Konto serwisowe `vpn-relay-gateway` z `roles/run.invoker` **tylko** na usłudze Cloud Run
   tej funkcji (`google_cloud_run_v2_service_iam_member`, nazwa usługi z
   `google_cloudfunctions2_function.vpn_relay_control.service_config[0].service`). Funkcja
   nadal nie ma publicznego invokera.
4. Specyfikacja OpenAPI:
   - trzy ścieżki z kontraktu,
   - `x-google-backend` z `address` = URI funkcji, `path_translation: APPEND_PATH_TO_ADDRESS`
     i `jwt_audience` = URI funkcji,
   - `securityDefinitions` typu `apiKey` w nagłówku `x-api-key`,
   - limit `x-google-management` / `x-google-quota`, np. 30 zapytań na minutę na projekt.
5. Zasoby: `google_api_gateway_api`, `google_api_gateway_api_config` (z
   `api_config_id_prefix` + `lifecycle { create_before_destroy = true }`, bo konfiguracji
   nie da się edytować w miejscu; `gateway_config.backend_config.google_service_account` =
   konto z pkt 3) i `google_api_gateway_gateway` w regionie obsługiwanym przez API Gateway
   (patrz „Do weryfikacji”). Region gatewaya nie musi być taki sam jak region funkcji, a
   dodatkowe opóźnienie przy start/stop nie ma znaczenia.
6. `google_apikeys_key` z `restrictions.api_targets` ograniczonym do usługi zarządzanej
   gatewaya (`google_api_gateway_api.managed_service`). Opcjonalnie dodatkowo
   `android_key_restrictions` (nazwa pakietu + SHA-1 certyfikatu podpisującego). To jednak
   wyłącza wywołania z HTTP Shortcuts i `curl`, więc decyzja należy do Ciebie.
7. Outputy: `vpn_relay_api_url` (default hostname gatewaya) i `vpn_relay_api_key`
   (`sensitive = true`). Klucz odczytuje się przez `terraform output -raw vpn_relay_api_key`
   i **nigdy** nie commituje.
8. Nowy cel `make gcloud-vpn-api-status`: `curl` z kluczem z outputu, jako szybki test
   end-to-end.

**Ryzyko: wymuszone odtworzenie VM.** `terraform plan` od dawna pokazuje
`google_compute_instance.vpn_relay must be replaced` (świadomie odłożona zmiana
`metadata_startup_script`, opisana w `infra/gcloud/terraform/CLAUDE.md`). Zwykłe
`terraform apply` przy tym etapie **odtworzy VM**: powstanie nowe CA OpenVPN, wszystkie
profile `.ovpn` łącznie z NAS-em przestaną działać, a ręczne poprawki (`client-template.txt`,
ewentualne `ccd/android-phone`) przepadną. Są dwie opcje:
- stosować `terraform apply -target=...` tylko dla nowych zasobów i funkcji,
- albo dodać `lifecycle { ignore_changes = [metadata_startup_script] }` do
  `google_compute_instance.vpn_relay`. To jest prostsze na przyszłość, ale wtedy zmiany
  skryptu trzeba wymuszać świadomie (`-replace`).

Rekomendacja: `ignore_changes`, z adnotacją w `CLAUDE.md`. Przed każdym `apply` sprawdzić w
planie, że `vpn_relay` **nie** jest na liście do odtworzenia.

**Weryfikacja:**
- `curl -H "x-api-key: …" https://<gateway>/status` → 200 + JSON,
- bez klucza → 401/403,
- bezpośrednie wywołanie URL funkcji bez tokenu → 403 (dalej niepubliczna),
- `make gcloud-vpn-*` działają jak wcześniej,
- cykl start → `RUNNING` + `external_ip` → stop → `TERMINATED`.

### Etap 3 — aplikacja na Androida

Nowy podprojekt `android_vpn_control/` w monorepo, z własnym `CLAUDE.md` i wpisem w tabeli
podprojektów w głównym `CLAUDE.md`.

**Stos:**
- Kotlin, Jetpack Compose, `minSdk 26`,
- OkHttp + kotlinx.serialization,
- DataStore na ustawienia; klucz API szyfrowany kluczem z Android Keystore (np. przez
  Tink). `androidx.security:security-crypto` (EncryptedSharedPreferences) jest
  deprecated, więc go nie używamy.

**Funkcje (MVP):**
1. **Ustawienia:** URL gatewaya i klucz API, wpisywane ręcznie lub skanowane z kodu QR
   wygenerowanego lokalnie z outputów Terraform. Klucz nie trafia do repo ani do APK.
2. **Ekran główny:** stan VM (zatrzymana / uruchamia się / działa / zatrzymuje się), IP,
   hostname, przycisk Start/Stop (Stop z potwierdzeniem), odświeżanie.
3. **Czekanie na gotowość po starcie:** odpytywanie `/status` co 5 s (maks. ok. 3 min), aż
   pojawi się `RUNNING` + `external_ip`, a następnie sprawdzenie, że
   `vpn.gcloud.lenie-ai.eu` rozwiązuje się na ten adres (TTL rekordu to 60 s; startup-script
   aktualizuje DNS kilkadziesiąt sekund po boocie). Dopiero wtedy stan „gotowy do
   połączenia”.
4. **Kafelek Quick Settings** (`TileService`): pokazuje stan, a dotknięcie przełącza
   start/stop.
5. **Połączenie VPN:** po stanie „gotowy” przycisk „Połącz”:
   - **OpenVPN for Android** (`de.blinkt.openvpn`) ma publiczne API (intent / AIDL)
     pozwalające połączyć profil o podanej nazwie; nazwa profilu jest w ustawieniach,
   - **OpenVPN Connect** nie ma takiego API, więc aplikacja tylko go otwiera.

   Rekomendacja: OpenVPN for Android.

**Funkcje (po MVP):**
6. **Przypomnienie o włączonej VM:** WorkManager co godzinę sprawdza `/status`. Jeśli VM
   działa dłużej niż N godzin (domyślnie 3), wysyła powiadomienie z akcją „Zatrzymaj”.
7. Widget na ekranie głównym (stan + Start/Stop).

**Build i dystrybucja:**
- Gradle wrapper w repo.
- Keystore do podpisu release'ów **poza repo** (lokalnie; ścieżka i hasła przez
  `local.properties` / zmienne środowiskowe, wykluczone w `.gitignore`).
- Instalacja przez `adb install` lub przesłanie APK.
- Opcjonalnie workflow GitHub Actions budujący debug APK i uruchamiający testy
  (bez podpisu release).

**Testy:** JUnit dla klienta API i maszyny stanów (start → polling → gotowy), z
`MockWebServer` (OkHttp) do symulacji odpowiedzi, timeoutów i 401/429.

**Weryfikacja:** na fizycznym telefonie przez LTE (Wi-Fi wyłączone): Start z kafelka →
„gotowy” → Połącz → otwarcie `http://192.168.200.7:5055/` → Rozłącz → Stop → po chwili
`TERMINATED`.

### Etap 4 (opcjonalny) — automatyczne zatrzymanie jako siatka bezpieczeństwa

Niezależnie od przypomnień w aplikacji:
- **Cloud Scheduler** codziennie o 02:00 (Europe/Warsaw) wywołuje funkcję z akcją `stop`
  (OIDC z osobnym kontem z `run.invoker`). Mieści się w darmowych 3 zadaniach.
- **Alternatywa po stronie VM:** cron sprawdza plik statusu OpenVPN i wyłącza VM, gdy przez
  60 minut nie jest połączony żaden klient **poza `nas`** (NAS jest połączony zawsze, gdy
  VM działa, więc „zero klientów” nigdy by nie wystąpiło). Wymaga to zmiany na VM, czyli
  ręcznej konfiguracji lub odtworzenia instancji (patrz ryzyko w Etapie 2), dlatego
  preferowany jest Scheduler.

### Etap 5 — dokumentacja

- `infra/gcloud/terraform/CLAUDE.md`: API Gateway, klucz, `ignore_changes`, nowe cele `make`.
- ADR-023: addendum, że część „Start/stop control” jest zrealizowana przez API Gateway +
  aplikację Android zamiast Firebase Hosting.
- `android_vpn_control/CLAUDE.md` oraz tabela podprojektów w głównym `CLAUDE.md`.
- Status tego dokumentu.

## Koszt

Bez zmian względem szacunku ADR-023 (~$1-2.5 miesięcznie):
- API Gateway jest darmowy do 2 mln wywołań miesięcznie,
- klucze API są darmowe,
- Cloud Scheduler: 3 zadania darmowo.

Największym ryzykiem kosztowym pozostaje zapomniana włączona VM, i właśnie temu służą
przypomnienia z Etapu 3 i auto-stop z Etapu 4.

## Do weryfikacji przed implementacją

- **Region API Gateway.** API Gateway jest dostępny tylko w części regionów, a
  `europe-central2` (Warszawa) prawdopodobnie do nich nie należy. Trzeba sprawdzić aktualną
  listę w dokumentacji (*API Gateway → Deployment model / locations*) i wybrać najbliższy
  region europejski. Nie zostało to zweryfikowane przy pisaniu planu, bo dokumentacja była
  niedostępna z sesji, w której powstał ten dokument.
- Czy `google_api_gateway_*` wymagają jeszcze providera `google-beta` w wersji zgodnej z
  `~> 6.27`.
- Czy klucz z `android_key_restrictions` jest honorowany przez API Gateway dla wywołań z
  natywnej aplikacji (nagłówki `X-Android-Package` / `X-Android-Cert`). Jeśli tak, warto
  go włączyć po porzuceniu HTTP Shortcuts.
- Aktualny sposób wywołania połączenia profilu w OpenVPN for Android (intent vs AIDL) w
  bieżącej wersji aplikacji.
