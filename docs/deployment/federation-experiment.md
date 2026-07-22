# Otwarte pytanie: wymiana danych między instancjami Lenie AI

Status: **bardzo wczesny eksperyment myślowy — samo pytanie, nie plan.** Zebrane, żeby nie zgubić kontekstu, gdy temat wróci.  
Powiązane: [README.md](README.md) · [nas/multi-user-household.md](nas/multi-user-household.md) · [commercial-multi-tenant-scaling-experiment.md](commercial-multi-tenant-scaling-experiment.md) · [ADR-015](../adr/adr-015-uuid-as-global-document-identifier.md)

## Pytanie

Jednym z możliwych przyszłych etapów jest wymiana informacji między różnymi, osobnymi instancjami Lenie AI — np. moją drugą instalacją, albo instalacją znajomego, który też zbiera i obrabia artykuły. To jest inna oś niż wielu użytkowników w jednej instancji (`nas/multi-user-household.md`, `commercial-multi-tenant-scaling-experiment.md`) — tu chodzi o **wiele niezależnych instancji wymieniających się danymi**, nie o role wewnątrz jednej.

## Czy obecny model to uwzględnia? Częściowo — jeden fundament już istnieje

**[ADR-015](../adr/adr-015-uuid-as-global-document-identifier.md) (2026-03-30) został podjęty właśnie z myślą o tym scenariuszu.** Dokumenty mają dziś globalnie unikalny `uuid` zamiast lokalnego, auto-increment `id` — cytat z ADR: „Cross-instance synchronization — no way to match documents between NAS and AWS databases” był jednym z motywujących problemów. To oznacza, że **identyfikacja tego samego dokumentu na dwóch instancjach już działa** — nie trzeba by wymyślać deduplikacji od zera.

Poza tym jednym elementem **nic więcej w architekturze tego nie zakłada ani nie ułatwia**:

- brak protokołu synchronizacji (co, kiedy, w którą stronę);
- brak modelu zaufania między właścicielami instancji (czy w ogóle ufam drugiej instancji, czy tylko wybranym danym z niej);
- brak selektywnego udostępniania (chcę dzielić się np. tylko artykułami z tagiem X, nie całą biblioteką, nie notatkami osobistymi);
- brak rozwiązywania konfliktów (ten sam dokument zmieniony/otagowany różnie na obu instancjach);
- brak rozróżnienia „mój dokument” vs „dokument otrzymany od kogoś” (kto jest źródłem prawdy po synchronizacji?);
- embeddingi są generowane per `EMBEDDING_MODEL` skonfigurowany lokalnie — dwie instancje mogą mieć niekompatybilne wektory, więc synchronizacja samego wyszukiwania semantycznego nie jest trywialna;
- NER/tagi/encje są dziś przycięte do `ner_exclusions` i słowników per instancja — mogą się różnić między instancjami dla tego samego tekstu.

## Co NIE robić teraz

Nic w kodzie. To jest jedyny dokument w `docs/deployment/`, który nie ma dziś żadnego „taniego kroku” do zrobienia — nawet model danych (poza już zrobionym ADR-015) nie jest jasny na tyle, żeby cokolwiek przygotowywać na zapas. Warto go odświeżyć, gdy pojawi się konkretny drugi właściciel instancji, z którym rzeczywiście chcę wymieniać dane.
