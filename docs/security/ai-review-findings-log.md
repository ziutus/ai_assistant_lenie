# Dziennik przeglądów bezpieczeństwa przez modele AI

**Świadomy wyjątek od zasady „docs opisuje bieżący stan".** Ten plik jest
celowo rejestrem historycznym: zapisuje, *który* model AI, *kiedy* i *jakie*
problemy wykrył podczas przeglądu kodu Lenie. Cel — po roku, dwóch móc porównać,
jak poszczególne modele radziły sobie z wyszukiwaniem błędów i jak to się
zmieniało w czasie.

Nie usuwać starych wpisów i nie przepisywać ich na „stan bieżący". Bieżący stan
zabezpieczeń opisują [profil lokalny](local-development-security.md) i
[checklista gotowości](production-readiness.md); tutaj liczy się data i autorstwo
znaleziska.

## Jak dodać wpis

Nowe przeglądy dopisujemy **na górze** listy. Jeden wpis = jeden przegląd przez
jeden model. W nagłówku: data przeglądu i model wraz z dostawcą. W treści:
analizowany commit/zakres, tabela znalezisk (problem, severity, status z linkiem
do PR-a jeśli naprawione) oraz co świadomie zostało poza zakresem lub czego nie
sprawdzano.

---

## 2026-09-06 — Astra (OpenAI)

Zakres: przegląd `origin/main` @ `a80f11bb9874495e1e770ef76f96f14191c5f0b9`
z prośbą o oddzielenie błędów kodu od świadomych uproszczeń lokalnego środowiska.

| # | Problem | Severity | Status |
|---|---|---|---|
| 1 | `GET /website_delete` usuwa dokumenty — dozwolone dla klucza `read_only`, bo globalny gate przepuszcza `GET`/`HEAD`/`OPTIONS` niezależnie od skutków operacji | Wysoki | Naprawione — [PR #609](https://github.com/ziutus/ai_assistant_lenie/pull/609) (endpoint zmieniony na `DELETE`) |
| 2 | SSRF w pobieraniu feedów (`library/feed_parser.py:fetch_entries`) — brak walidacji celu, automatyczne przekierowania; klucz `user` może podmienić URL istniejącego feedu i zlecić check, worker wykonuje żądanie | Wysoki | Naprawione — [PR #609](https://github.com/ziutus/ai_assistant_lenie/pull/609) (`library/safe_http.py`: DNS raz, przypięcie adresu, walidacja każdego hopu) |
| 3 | `OPTIONS /uploads` zwraca listę plików (nazwy, klucze obiektów, rozmiary) bez uwierzytelnienia — handler nie przerywa na preflighcie | Średni | Naprawione — [PR #609](https://github.com/ziutus/ai_assistant_lenie/pull/609) (`OPTIONS` → puste `204` przed dostępem do storage) |
| 4 | Nieograniczony cache błędnych kluczy API (`library/auth.py:InProcessApiKeyCache`) — brak limitu wpisów, wygasłe wpisy usuwane dopiero przy ponownym odpytaniu o ten sam hash; rotacja losowych kluczy rośnie w pamięci i generuje ruch do bazy | Średni | Naprawione — [PR #609](https://github.com/ziutus/ai_assistant_lenie/pull/609) (limit 10 000 wpisów + odzysk wygasłych) |

Wskazane jako poza zakresem czterech poprawek:

- Ta sama luka DNS rebinding / TOCTOU w starszym `library/website/website_download_context.py` (`validate_url_target` sprawdza DNS, a `requests` rozwiązuje go ponownie przy połączeniu). Zawężone i naprawione w tym samym [PR #609](https://github.com/ziutus/ai_assistant_lenie/pull/609) — konkretny kształt luki doprecyzował model **GPT-5-Codex (OpenAI)** w trakcie implementacji.
- `infra/aws/serverless/lambdas/app-server-db/lambda_function.py` rozsyła usuwanie po ścieżce bez sprawdzania metody HTTP — uśpiony kod AWS, świadomie nie zmieniany.
- Registry na NAS bez TLS/uwierzytelniania, fallback hasła bazy, ekspozycja portów — sklasyfikowane jako uproszczenia infrastrukturalne, nie błędy kodu (patrz [profil lokalny](local-development-security.md)).

Nie sprawdzano: reguł zapory, ekspozycji usług spoza LAN, aktualnego hasła
działającej bazy ani pełnego audytu zależności/CVE. Nie wykonywano żądań
atakujących do NAS-a ani operacji na jego bazie.
