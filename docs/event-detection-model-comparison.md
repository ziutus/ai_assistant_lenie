# Wykrywanie wydarzeń z datą: porównanie modeli i decyzja o trybie z wiedzą

Data pomiaru: 2026-11-19. Dotyczy panelu „Wydarzenia z datą w rozdziale” na `/ner/:id/:rozdział`
(`POST /document/<id>/chapter/<n>/detect_events`, kod: `backend/library/timeline_events.py`).

## Wniosek w pięciu zdaniach

1. Domyślny model (Bielik 11B v3.0) wykrywa tylko wydarzenia, które tekst **sam opisuje wraz z datą**. Na rozdziale, w którym
   autor przywołuje historyczne analogie, znalazł 1 z 3 wydarzeń, które człowiek uznał za oczywiste.
2. Przyczyny są trzy i tylko jedna dotyczy rozmiaru modelu: (a) zakres wiedzy modelu, (b) prompt **zakazuje** wiedzy zewnętrznej,
   (c) kod odrzuca zapis „Monachium 38”, bo przyjmuje tylko lata 3–4-cyfrowe.
3. Samo podmienienie modelu na większy nic by nie dało, bo prompt i walidator uniemożliwiają użycie wiedzy. Dlatego zmieniono
   **sposób analizy**, a nie tylko model.
4. Nowy tryb „Analogie historyczne” pozwala modelowi podać rok wydarzenia, które tekst tylko nazywa. Rok jest oznaczony w opisie
   propozycji jako pochodzący z wiedzy modelu, a człowiek nadal zatwierdza każdą propozycję.
5. Na tym samym rozdziale Claude Sonnet 5.5 i Claude Fable 5.2 w nowym trybie znalazły wszystkie trzy wydarzenia. Koszt
   rozdziału to ok. 0,09 USD (Sonnet) i ok. 0,43 USD (Fable). Tryb jest włączany świadomie i **nie zmienia domyślnego modelu**.

## Jak działa wykrywanie (co faktycznie decyduje o wyniku)

Model dostaje fragment rozdziału (do 10 000 znaków) i zwraca listę `{type, date_text, description, quote}`. Zanim propozycja trafi do
`document_events`, przechodzi cztery filtry po stronie kodu:

| Filtr | Reguła | Skutek |
|---|---|---|
| Cytat | `quote` musi występować **dosłownie** we fragmencie (ujednolicana jest tylko typografia, wielkość liter **nie**) | model „poprawiający” cytat (`54` → `1954`, `To` → `to`) traci wydarzenie |
| Typ | publikacje (badanie, książka) trafiają do źródeł informacji, nie do wydarzeń | celowe |
| Data | `date_text` musi dać się znormalizować (`normalize_date_text`): pełna data, miesiąc, rok 3–4-cyfrowy, wiek, dekada | zapis „Monachium 38” lub „38” jest odrzucany |
| Zignorowane | fragment, który człowiek już odrzucił, nie wraca | celowe |

Prompt mówi wprost: „wyodrębnij wyłącznie wydarzenia opisywane w tekście, którym tekst przypisuje datę albo okres. Nie dodawaj wiedzy
zewnętrznej ani nie zgaduj dat.” To rozsądne dla dat zapisanych w tekście, ale wyklucza dokładnie ten przypadek, w którym autor
przywołuje wydarzenie samą nazwą („Monachium 38”, „Jałta”, „kongres westfalski”).

## Pomiar

**Materiał:** dokument 11265 (wideo „Trump, Putin i Xi: szczyt trzech słabości”), rozdział 2 „Szczyt zmierzchu mocarstw”,
26 862 znaków, 3 fragmenty. Autor porównuje szczyt do trzech historycznych wydarzeń. **Wydarzenia docelowe** wskazał użytkownik:

| Wydarzenie | Jak występuje w tekście |
|---|---|
| Kongres westfalski 1648 | „kongres westfalski 1648 rok” (rok wprost) |
| Genewa 1954 | „Genewa 1954 rok” i kilka razy „Genewa 54 roku” |
| Monachium 38 | tylko „Monachium 38” (rok skrócony, bez „roku”) |

**Metoda:** produkcyjne `extract_document_events()` (te same wskazówki NER, ta sama walidacja) na każdym modelu z listy
`chapter_analysis`, bez zapisu do `document_events`. Przechwycono surowe odpowiedzi modeli i wyniki normalizatora dat, żeby odróżnić
„model nie zwrócił” od „model zwrócił, a kod odrzucił”.

### Tryb domyślny (prompt sprzed zmiany)

| Model | Zapisane zdarzenia | Westfalia 1648 | Genewa 1954 | Monachium 38 |
|---|---:|---|---|---|
| **Bielik 11B v3.0** (domyślny) | 1 | nie zwrócił | zapisane | nie zwrócił |
| Gemini 2.5 Flash Lite (OpenRouter) | 4 | zapisane | zapisane | zwrócił, **odrzucona data** |
| Gemma 3 27B (OpenRouter) | 3 | zapisane | zapisane | nie zwrócił |
| Mistral Small 3.2 24B (OpenRouter) | 3 | zapisane | zwrócił, **odrzucony cytat** („54” → „1954”) | nie zwrócił |
| GPT-4o mini (OpenRouter) | 3 | zwrócił, **odrzucony cytat** („to” zamiast „To”) | zapisane | nie zwrócił |
| Llama 3.1 8B (OpenRouter) | 26 | zwrócił, **odrzucony cytat** (z innego miejsca) | zapisane | zwrócił, **odrzucona data** |

Pięć wpisów z listy wyboru **nie dało się uruchomić**: GPT-4o mini bezpośrednio u OpenAI (brak kredytów), oba Gemini na Vertex AI
(wygasła autoryzacja `gcloud`), Bielik v2.3 (CloudFerro odpowiada 404) i Qwen 2.5 (wycofany z OpenRouter). Dwa ostatnie usunięto z
konfiguracji w tej samej zmianie. Pozostałe trzy (OpenAI bezpośrednio i oba Gemini na Vertex) ukryto 2026-11-19 (`retired`), a wycofany
Gemini 2.5 Flash Lite przez OpenRouter usunięto: na razie zostają tylko dostawcy OpenRouter i CloudFerro, żeby łatwiej kontrolować wydatki.
Przywrócenie któregoś to jedno `PATCH /llm_models/<id>` z `status: active`.

### Klasy porażek

| Klasa | Przykład | Czyja to wina | Czy większy model pomoże |
|---|---|---|---|
| **A. Model nie zwraca wydarzenia** | Bielik: Westfalia i Monachium | wiedza i skłonność modelu do przywoływania analogii | częściowo |
| **B. Model zwraca, odrzuca cytat** | Mistral „54” → „1954”, GPT-4o mini „to” zamiast „To” | ścisła, wrażliwa na wielkość liter walidacja cytatu | nie (to kod) |
| **C. Model zwraca, odrzuca data** | „Monachium 38” u Gemini i Llamy | normalizator nie zna lat 2-cyfrowych | nie (to kod i prompt) |
| **D. Szum** | Llama 8B: 26 zdarzeń, wiele nie jest wydarzeniami | zbyt mały model | tak |
| **E. Dostępność** | brak kredytów, wygasła autoryzacja, martwe modele | konfiguracja | nie dotyczy |

Najważniejsza obserwacja: klasy B i C pokazują, że część strat nie zależy od modelu. „Monachium 38” **nie mogło** zostać zapisane
przez żaden model w trybie domyślnym, bo nie ma w tekście roku, który normalizator przyjmie, a prompt zabrania go dopowiedzieć.

## Ograniczenia Bielika w tym zadaniu

- **Zakres wiedzy.** 11B parametrów to za mało, żeby pewnie rozpoznać analogię historyczną po samej nazwie. Bielik nie zwrócił Westfalii,
  choć rok stał w tekście obok („kongres westfalski 1648 rok”), więc część strat to także niedokładne czytanie długiego fragmentu.
- **Niestabilność.** W trybie domyślnym znalazł Genewę. W trybie z wiedzą (niżej) znalazł Monachium, a Genewy nie. W obu przebiegach
  1 z 3, za każdym razem inne. To jeden przebieg każdego rodzaju, więc to sygnał, nie statystyka.
- **Dużo odrzuceń przy cytatach.** W trybie z wiedzą 4 propozycje odpadły z powodu cytatu niebędącego dosłownym fragmentem.
- **Czego Bielik nie traci.** Jest tani (ok. 0,56 EUR za milion tokenów, ok. 0,009 EUR za cały rozdział), po polsku i ma docelowo działać
  lokalnie. Zakładamy, że wystarcza dla wydarzeń zapisanych w tekście z pełną datą, ale ten pomiar tej tezy nie sprawdzał (żadne z trzech
  wydarzeń docelowych nie było takim przypadkiem w czystej postaci). Dlatego Bielik zostaje domyślny ze względu na koszt i lokalność,
  a nie dlatego, że to wykazano.

## Decyzja i powody

**Co zmieniono**

1. **Nowy tryb `knowledge`** w `detect_events`. Model może wpisać rok (`year`) wydarzenia, które tekst tylko nazywa. Rok jest używany
   wyłącznie wtedy, gdy zapis z tekstu nie daje się znormalizować (rok z tekstu zawsze wygrywa). Opis propozycji kończy się
   adnotacją „(rok ustalony przez model z jego wiedzy, nie odczytany z tekstu)”. Cytat nadal musi być dosłowny.
2. **Dwa modele frontier na liście wyboru** (przez OpenRouter): `anthropic/claude-sonnet-5.5` (2/10 USD za milion tokenów) i
   `anthropic/claude-fable-5.2` (8/40). Ich identyfikatory sprawdzono w publicznym katalogu OpenRouter 2026-11-19.
3. **Pole wyboru „Analogie historyczne (rok z wiedzy modelu)”** pod wyborem modelu w panelu.
4. **Sprzątanie listy:** usunięto Bielik 11B v2.3 i Qwen 2.5 7B, których nie dało się wywołać.

**Rozważone i odrzucone**

| Opcja | Dlaczego nie |
|---|---|
| Frontier jako model domyślny | koszt przy masowej analizie książek, wysyłanie tekstu do zewnętrznego pośrednika, sprzeczność z planem lokalnego Bielika |
| Tylko mocniejszy model, bez zmiany promptu | prompt zakazuje wiedzy, a normalizator odrzuca „38”: nic by się nie zmieniło |
| Dopracować prompt Bielika | prompt nie doda modelowi wiedzy; zostaje problem klas A i C |
| Tylko skill `/lenie-chapter-world-events` | działa (czyta rozdział frontierem i zapisuje po zgodzie), ale poza interfejsem i bez kosztów widocznych w panelu |
| Osobny tryb włączany świadomie (**wybrane**) | zachowuje tani domyślny przepływ, a frontier pojawia się tam, gdzie jest potrzebny, z oznaczeniem, że rok pochodzi z wiedzy |

## Pomiar po zmianie (tryb z wiedzą)

| Model | Zapisane zdarzenia | w tym lat z wiedzy | Westfalia 1648 | Genewa 1954 | Monachium 38 | Koszt rozdziału |
|---|---:|---:|---|---|---|---:|
| **Claude Sonnet 5.5** | 9 | 7 | tak (rok z tekstu) | tak („Genewa 54” → 1954) | tak („Monachium 38” → 1938) | 0,091 USD |
| **Claude Fable 5.2** | 10 | 7 | tak | tak | tak | 0,428 USD |
| Bielik 11B v3.0 | 1 | 1 | nie | nie | tak | 0,009 EUR |

**Jakość pozostałych propozycji Sonneta** (ręczny przegląd wszystkich 9): Jałta 1945, aneksja Krymu 2014, aneksja Donbasu 2022,
proces norymberski 1945, rozejm w Korei 1953 (rok z tekstu), konferencja jałtańska 1945. Lata są poprawne. Jedna słabość: opis Genewy
zaczyna się od klęski pod Dien Bien Phu zamiast od samej konferencji, więc opis wymaga redakcji przed dodaniem do rejestru.

## Kiedy który model

| Sytuacja | Model | Tryb |
|---|---|---|
| Masowa analiza, wydarzenia opisane z datą | Bielik 11B v3.0 (lokalnie docelowo) | domyślny |
| Rozdział z analogiami historycznymi, krótki tekst, ważny dokument | Claude Sonnet 5.5 | „Analogie historyczne” |
| Trudny lub bardzo ważny rozdział, porównanie wyników | Claude Fable 5.2 | „Analogie historyczne” |
| Dokument prywatny | tylko model lokalny/CloudFerro | domyślny |

Przy modelu frontier cały rozdział trafia do zewnętrznego pośrednika (OpenRouter). Panel już to sygnalizuje w wyborze modelu, a
`OPENROUTER_ENABLED` musi być włączone.

## Ograniczenia pomiaru i znane niedociągnięcia

**Pomiar:** jeden dokument, jeden rozdział, jeden przebieg na model (temperatura 0,1, wynik nie jest deterministyczny), trzy wydarzenia
wskazane przez człowieka jako wzorzec. To ilustracja mechanizmu, nie benchmark: nie mierzy ani precyzji, ani pełności na szerszym
korpusie. Rok z wiedzy modelu może być błędny. Dlatego jest oznaczony w opisie i wymaga przeglądu.

**Niezałatane w tej zmianie** (osobne, drobne poprawki):

- porównanie cytatu rozróżnia wielkość liter (klasa B),
- normalizator nie przyjmuje lat 2-cyfrowych w trybie domyślnym (klasa C; w trybie z wiedzą omija je pole `year`),
- w jednym z przebiegów w trybie z wiedzą logi zgłosiły odpowiedź, której nie dało się odzyskać jako JSON; nie ustalono, który model
  ani dlaczego (możliwy trop: limit `max_token_count=4000` przy obszernej odpowiedzi),
- `detect_events` nie sprawdza, czy przekazany `model` jest na liście dozwolonych (sprawdza to dopiero routing w `ai_ask()`).

## Jak powtórzyć pomiar

Wywołaj `timeline_events.extract_document_events(session, doc, model, chapter_position=2, editor_numbering=True, knowledge=True)` dla
dokumentu 11265 (funkcja niczego nie zapisuje), a przed nią podstaw w module `timeline_events` obudowy na `ai_ask` i
`normalize_date_text`, żeby zobaczyć surowe odpowiedzi i odrzucone daty. Każde wywołanie zapisuje wiersz w `llm_usage_logs`
(operacja `timeline_event_extraction`), więc koszt jest widoczny na `/llm-costs`.

Zobacz też: [llm-features-howto.md](llm-features-howto.md) (jak budować funkcje oparte na LLM),
[ADR-032](adr/adr-032-llm-models-db-backed.md) (lista modeli w bazie), [ADR-034](adr/adr-034-world-events-registry.md)
(rejestr wydarzeń świata).
