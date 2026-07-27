# Feed i `feed-review` — przepływy

Ten dokument opisuje aktualny przepływ materiałów z feedów: od pobrania wpisu, przez decyzję użytkownika, po import dokumentu, odłożenie do późniejszego przeglądu, ignorowanie i cofnięcie decyzji.

## Pojęcia

- `FeedSource` — konfiguracja źródła feedu.
- `FeedItem` — pojedynczy wpis znaleziony w feedzie; przechowuje URL, tytuł, daty, status i ewentualne powiązanie z dokumentem.
- `Document` — materiał zaimportowany do bazy, np. `link`, `webpage` albo `youtube`.
- `ContentGroup` — temat lub priorytet przypisany do wpisu albo dokumentu.
- `FeedReviewDecision` — zapis decyzji kuratorskiej, zawierający stan przed/po, batch, użytkownika i grupy.

## Pobieranie feedu

```mermaid
flowchart TD
    A[Job feed_check] --> B[Pobierz URL FeedSource]
    B --> C[Parsuj wpisy i canonical URL]
    C --> D{Wpis już istnieje?}
    D -- Nie --> E[Utwórz FeedItem: new]
    D -- Tak --> F[Aktualizuj last_seen_at i dane wpisu]
    E --> G[Zastosuj reguły pomijania]
    F --> G
    G --> H{Pasuje do reguły?}
    H -- Tak --> I[ignored + ignored_pattern]
    H -- Nie --> J[Pozostaw status bez zmiany]
    J --> K[Opcjonalnie: sugestia Bielika]
```

Feed nie tworzy dokumentu podczas samego sprawdzania źródła. Dokument powstaje dopiero po jawnej decyzji importu albo przez inny mechanizm importu.

## Lifecycle `FeedItem`

```mermaid
stateDiagram-v2
    [*] --> new: nowy wpis
    new --> saved_for_later: zachowaj link / później
    new --> imported: import dokumentu
    new --> skipped: pomiń
    new --> ignored: ignoruj
    new --> error: błąd importu
    new --> llm_analysis_requested: analiza grup
    llm_analysis_requested --> saved_for_later
    llm_analysis_requested --> imported
    llm_analysis_requested --> skipped
    llm_analysis_requested --> ignored
    llm_analysis_requested --> error
    saved_for_later --> new: przywróć do nowych
    saved_for_later --> imported: import później
    saved_for_later --> skipped: nie dodawaj
    saved_for_later --> ignored: ignoruj
    error --> saved_for_later
    error --> imported
    error --> skipped
    error --> ignored
```

Status `saved_for_later` może oznaczać zarówno sam zachowany URL, jak i URL z już utworzonym dokumentem. Rozstrzyga to `document_id`.

## Decyzje w `feed-review`

```mermaid
flowchart LR
    N[Nowe]
    N --> L[Zachowaj tylko link do oceny]
    N --> I[Zaimportuj jako link]
    N --> IR[Zaimportuj jako link i zapisz do przeczytania]
    N --> W[Zaimportuj jako webpage]
    N --> Y[Zaimportuj jako film]
    N --> S[Pomiń]
    N --> X[Ignoruj]
    L --> Q[Do przeczytania / obejrzenia\nFeedItem saved_for_later\nbez dokumentu]
    I --> D1[Document link\nFeedItem imported]
    IR --> D2[Document link\nFeedItem saved_for_later]
    W --> D3[Document webpage\nFeedItem imported]
    Y --> D4[Document youtube\nFeedItem imported]
    S --> K[FeedItem skipped]
    X --> Z[FeedItem ignored]
```

| Przycisk | Dokument | Status po akcji | Późniejsza akcja |
|---|---|---|---|
| `Zachowaj tylko link do oceny` | nie | `saved_for_later` | przeczytaj, zaimportuj, pomiń albo ignoruj |
| `Zaimportuj jako link` | `link` | `imported` | dokument jest już zachowany w bazie |
| `Zaimportuj jako link i zapisz do przeczytania` | `link` | `saved_for_later` | dokument i wpis są w kolejce późniejszej |
| `Zaimportuj jako webpage` | `webpage` | `imported` | dokument trafia do dalszego przetwarzania |
| `Zaimportuj jako film` | `youtube` | `imported` | dokument trafia do dalszego przetwarzania |

Przykład: aktualizowana lista książek powinna użyć `Zachowaj tylko link do oceny`. Zachowujemy URL, nie pobieramy treści i później możemy wpis zignorować.

## Import dokumentu

```mermaid
sequenceDiagram
    actor U as Użytkownik
    participant UI as feed-review
    participant API as Feed API
    participant DB as PostgreSQL
    participant DS as DocumentService
    U->>UI: wybiera typ importu
    UI->>API: POST /feed_items/:id/import
    API->>DB: pobierz FeedItem i zablokuj canonical URL
    API->>DS: utwórz albo znajdź Document
    DS-->>API: document_id
    API->>DB: skopiuj grupy feedu do dokumentu
    API->>DB: ustaw status i document_id
    API->>DB: zapisz FeedReviewDecision
    DB-->>API: FeedItem + document_id
    API-->>UI: wynik decyzji
    UI->>UI: zaktualizuj kartę bez pełnego reloadu
```

Dla wariantu „link i zapisz do przeczytania” import tworzy dokument, ale końcowy status wpisu pozostaje `saved_for_later`.

## Grupy i sugestie Bielika

```mermaid
flowchart TD
    A[FeedItem lub Document] --> B[POST group-suggestions]
    B --> C[ContentGroupSuggestionRun]
    C --> D[Job content_group_suggest]
    D --> E[Bielik otrzymuje katalog aktywnych tematów]
    E --> F{Pasujący temat?}
    F -- Tak --> G[Sugestie z confidence i reason]
    F -- Nie --> H[no_match=true\nbez wymuszania grupy]
    G --> I[Akceptuj / odrzuć]
    I --> J[Membership source=llm_suggestion]
    K[Decyzje FeedReviewDecision] -. przyszły kontekst preferencji .-> E
```

Bielik wybiera wyłącznie istniejące tematy. Priorytet, np. `Może kiedyś`, jest decyzją użytkownika i nie powinien być sugerowany jako temat.

## Historia i cofanie decyzji

```mermaid
sequenceDiagram
    actor U as Użytkownik
    participant UI as Historia decyzji
    participant API as Feed API
    participant DB as PostgreSQL
    U->>UI: otwiera Historia decyzji
    UI->>API: GET /feed_review_decisions
    API->>DB: filtruj po feed_source_id, batch_id lub job_id
    DB-->>API: decyzje z poprzednim i nowym stanem
    API-->>UI: lista decyzji
    U->>UI: wybiera Cofnij
    UI->>API: POST /feed_review_decisions/:id/undo
    API->>DB: sprawdź, czy wpis nie zmienił się później
    alt stan zgodny
        API->>DB: przywróć status, document_id i grupy
        API->>DB: oznacz decyzję jako undone
        DB-->>API: wynik cofnięcia
    else wpis zmieniony
        API-->>UI: 409 — wymagana ręczna weryfikacja
    end
```

Cofnięcie importu odłącza dokument od wpisu feedowego, ale nie usuwa dokumentu. Chroni to dokumenty używane także przez inne wpisy lub źródła.

## Najważniejsze endpointy

- `GET /feed_items` — kolejka wpisów według statusu i źródła.
- `POST /feed_items/:id/import` — import z `document_type`: `link`, `webpage`, `youtube`; opcjonalnie `keep_for_review=true`.
- `POST /feed_items/:id/save-for-later` — zachowanie samego wpisu/URL w kolejce późniejszej.
- `POST /feed_items/:id/ignore` — ignorowanie według wzorca URL albo tytułu.
- `POST /feed_items/:id/restore` — przywrócenie do `new`.
- `GET /feed_review_decisions` — historia decyzji z filtrami `feed_source_id`, `batch_id`, `job_id`.
- `POST /feed_review_decisions/:id/undo` — bezpieczne cofnięcie pojedynczej decyzji.

## Dane audytowe użyteczne dla LLM

Każda decyzja zawiera m.in. statusy przed/po, grupy przed/po, `action`, `metadata`, `user_id`, `batch_id`, opcjonalny `job_id`, czas i informację o cofnięciu. Pozwala to później budować kontekst preferencji użytkownika. Cofnięte decyzje powinny być wykluczane albo oznaczane osobno podczas tworzenia takiego kontekstu.
