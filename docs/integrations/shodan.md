# Shodan

**Status: odłożone.** Dostęp do API Shodana istnieje (klucz, plan Membership),
ale bez stałego publicznego adresu IP integracja nie daje użytkowej wartości.
Wracamy do niej, gdy Lenie będzie miało stały adres.

## Dlaczego teraz nie

Głównym powodem integracji byłby **monitoring własnej powierzchni ataku**:
okresowy lookup publicznego adresu i alert przy nowym otwartym porcie lub nowym CVE.
Jedyny zasób, który mógłby być wystawiony do internetu, to brama VPN w Google Cloud
([ADR-023](../adr/adr-023-gcloud-vpn-relay-nas-access.md)). Dostaje ona **nowy,
dynamiczny adres IP przy każdym uruchomieniu**, więc:

- snapshoty i diffy po adresie IP nie mają ciągłości (każde uruchomienie to inny host),
- alerty sieciowe Shodana są przypisywane do konkretnych IP i przestałyby dotyczyć
  naszej bramy po jej restarcie,
- ręczne sprawdzenie adresu w panelu shodan.io po uruchomieniu bramy wystarcza
  i nie wymaga kodu.

Pozostałe scenariusze (enrichment domen i IP z dokumentów, OSINT firmowych domen
kontaktów, statystyki CVE) są na planie Membership zbyt ograniczone limitem
zapytań, by uzasadniać osobny moduł.

## Plan Membership (do weryfikacji przed pracą)

Wartości z pamięci, **sprawdzić** przez `GET https://api.shodan.io/api-info?key=...`
(zapytanie jest darmowe i zwraca plan oraz pozostałe kredyty):

- ok. 100 query credits i 100 scan credits miesięcznie,
- lookup pojedynczego hosta (`/shodan/host/{ip}`) nie zużywa query credits,
- wyszukiwanie (`/shodan/host/search`) zużywa kredyty, a część filtrów
  (np. `vuln:`) wymaga wyższego planu,
- monitoring sieci (alerty) obejmuje ograniczoną liczbę adresów (rząd 16).

## Co zmienia stały adres IP

Po uzyskaniu stałego publicznego IP (statyczny adres bramy albo stały adres plus
DNS) monitoring własnej powierzchni staje się sensowny. Zakres pierwszej wersji:

1. `backend/library/shodan_service.py`: klucz `SHODAN_API_KEY` z Vault, wywołania
   przez wspólną warstwę HTTP, cache w tabeli snapshotów (adres, JSON, data, TTL).
2. Ochrona kredytów: odczyt licznika z `api-info`, odmowa zapytań płatnych poniżej
   progu (np. 10 pozostałych).
3. Endpointy REST: lookup hosta z cache oraz status planu i kredytów.
4. Zadanie okresowe w workerze: lookup własnych adresów, diff względem poprzedniego
   snapshotu, alert przy nowym otwartym porcie.
5. Opcjonalnie skill do ręcznych zapytań (wzór: `lenie-person-lookup`).

Enrichment dokumentów (adresy IP znalezione w tekście, bez NER) dopiero po tym
etapie i tylko dla lookupów, które nie zużywają kredytów.

## Zasady

Klucz wyłącznie w Vault. Wzbogacamy domeny firm, nie domowe adresy osób prywatnych.
Ogólne zasady dla integracji: [README.md](README.md).
