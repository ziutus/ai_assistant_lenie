# Zdjęcia kontaktów, opisy i rodziny

## Użycie

Na karcie kontaktu ze zdjęciem:

1. Otwórz **Szczegóły zdjęcia** obok awatara lub w historii zdjęć.
   Uzupełnij **Twój opis zdjęcia**, np. „To mąż i dwoje dzieci; dzieci są
   bliźniętami i chodzą do grupy przedszkolnej Filipa”. Zapisz opis.
2. Wygeneruj opis jednym modelem albo wybierz **Wygeneruj i porównaj dwa opisy**.
   Wyniki Gemmy i Mistrala są widoczne obok siebie, z datą, liczbą tokenów
   i czasem wywołania. Błąd jednego modelu nie usuwa wyniku drugiego.
3. Otwórz **Utwórz kontakty członków rodziny**. Sprawdź nazwy robocze,
   relację drugiego rodzica, zaznacz bliźnięta na podstawie własnej wiedzy.
   Imiona i nazwiska można zostawić puste.
4. Opcjonalnie wyszukaj Filipa i wybierz właściwy rekord. Powstaną relacje
   „ta sama grupa przedszkolna” między nim a każdym nowym dzieckiem.
5. Sprawdź własną informację potwierdzającą relacje i utwórz rodzinę.
   Drugi rodzic może odziedziczyć grupy kontaktu; dzieci nie dziedziczą ich.
   Dla dzieci można wybrać osobną grupę.
6. Gdy poznasz imiona, edytuj istniejące kontakty. Identyfikatory, zdjęcie
   i relacje pozostaną. Nazwa robocza służy jako nazwa wyświetlana tylko wtedy,
   gdy nie ma imienia ani nazwiska. Jest też przeszukiwalna.

Numer „Dziecko 1/2” rozróżnia rekordy, nie identyfikuje osoby na fotografii.
Formularz tworzy nowe kontakty; istniejące osoby można połączyć dotychczasowym
formularzem powiązań. Swobodne polecenia tekstowe nie są parsowane przez ten
formularz — klient LLM może przygotować jawny, sprawdzalny payload API poniżej.

## Obrazy i modele

Opisy i klasyfikacja należą do `contact_photos`. Publiczny identyfikator to `id` (UUID),
a `storage_key` pozostaje kluczem głównym i kluczem pliku.
Wiele kontaktów może wskazywać ten sam rekord zdjęcia. Zmiana opisu jest wtedy
widoczna przy każdym z nich. Wymiana fotografii tworzy nowy, unikalny klucz
pliku i pusty rekord opisów. Odpięcie zdjęcia od jednego kontaktu nie usuwa
pliku ani wspólnych opisów. Nie zmieniamy mechanizmu `document_images`.

Integracja z miniaturami i podglądem z `main`: lista nadal pokazuje miniatury,
a kliknięcie zdjęcia otwiera powiększony podgląd. Nowe miniatury mają klucz
zależny od konkretnego pliku zdjęcia, aby wymiana zdjęcia rodzica nie zmieniała
miniatury przy dzieciach korzystających ze starego zdjęcia. Nazwy robocze są
wyświetlane również na oznaczeniach relacji na liście kontaktów.

`user_description` i jego wersja są niezależne od `ai_descriptions` — mapy
najnowszych wyników poszczególnych modeli. Ponowne generowanie zastępuje wynik
tylko wybranego modelu; nie jest to historia wszystkich generowań.
Każdy wynik ma identyfikator modelu, czas wygenerowania i odnośnik do rejestru
zużycia LLM. Wywołania są audytowane przez `ai_ask`, z operacją
`contact_photo_description`; rejestr zużycia nie otrzymuje obrazu ani opisu
użytkownika. Koszt pozostaje w centralnym mechanizmie `llm_usage_logs`;
bez wpisu w cenniku ma status `unknown`, a nie koszt zerowy.

Wykorzystywane identyfikatory Sherlocka:

- `google/gemma-4-31B-it`
- `mistralai/Mistral-Small-4-119B-2603`

Wymagany jest istniejący `CLOUDFERRO_SHERLOCK_KEY` i dostęp do obu modeli
w projekcie CloudFerro. Obraz trafia do istniejącego endpointu
`/openai/v1/chat/completions` jako data URL. Obsługiwane przez tę funkcję
są JPEG i PNG, maksymalnie 5 000 000 bajtów; GIF/WebP nadal mogą być zdjęciem
kontaktu, ale obecnie nie mają generowania opisu.

Modele otrzymują tę samą instrukcję opisu widocznej zawartości. Nie otrzymują
notatek, nazwisk, wiedzy użytkownika ani wzajemnych wyników. Nie mają zgadywać
tożsamości, małżeństwa, rodzicielstwa czy bliźniactwa. Relacje rodzinne powstają
wyłącznie z jawnych informacji podanych przez użytkownika. Zgodność dwóch
opisów nie jest potwierdzeniem faktu rodzinnego.

Dokumentacja dostawcy sprawdzona 2026-09-13:

- [Modele z obsługą obrazów](https://docs.cloudferro.com/en/latest/sherlock/Sherlock-AI-models-on-CloudFerro-Cloud.html)
- [Format zapytania vision](https://docs.cloudferro.com/en/latest/sherlock/Sherlock-vision-model-endpoint-on-CloudFerro-Cloud.html)

## API

Wszystkie operacje używają dotychczasowego uwierzytelnienia kontaktów.
`GET /contacts/{id}` zwraca dotychczasowe `photo_url` oraz obiekt `photo`:
`storage_key`, `user_description`, `user_description_revision`,
`ai_descriptions`, `id`, `subject_kind`, `people_count`, `classification_revision`,
`depicts_contact` i `link_revision`. Kontakt zwraca też `display_label` i wyliczone `display_name`.

Zapis własnego opisu:

```http
PATCH /contacts/{id}/photo/description
Content-Type: application/json

{"storage_key":"contacts/.../photo.jpg","user_description":"Moja wiedza","user_description_revision":0}
```

Pusty tekst czyści opis. Nieaktualna wersja opisu albo zmienione zdjęcie
zwracają 409, zachowując istniejące dane.

Generowanie jednego wyniku (porównanie to dwa niezależne żądania):

```http
POST /contacts/{id}/photo/describe
Content-Type: application/json

{"storage_key":"contacts/.../photo.jpg","model":"google/gemma-4-31B-it"}
```

Przed wywołaniem dostawcy transakcja DB jest zamykana. Zapis wyniku ponownie
sprawdza aktualne zdjęcie i wynik wybranego modelu pod blokadą wiersza.
Równoczesny zapis innego modelu lub notatki użytkownika nie jest nadpisywany.

Przykład jawnego polecenia utworzenia rodziny (ID, klucz, imiona i relacje
należy przygotować na podstawie aktualnych danych i polecenia użytkownika):

```http
POST /contacts/{id}/family
Content-Type: application/json

{
  "request_id": "5e4f0be1-972f-46c2-91e8-33716990df6b",
  "storage_key": "contacts/.../photo.jpg",
  "spouse": {"display_label": "Drugi rodzic — rodzina kontaktu"},
  "spouse_relationship": "mąż",
  "children": [
    {"display_label": "Dziecko 1 — rodzina kontaktu"},
    {"display_label": "Dziecko 2 — rodzina kontaktu"}
  ],
  "twins": true,
  "share_photo": true,
  "copy_parent_groups": true,
  "peer_contact_id": null,
  "children_group_id": null,
  "source_note": "Wiem, że to mąż i dwoje dzieci; dzieci są bliźniętami."
}
```

Zapis całej rodziny, relacji i informacji o źródle jest jedną transakcją.
Ponowienie identycznego payloadu z tym samym `request_id` zwraca wcześniejsze
identyfikatory, bez nowych rekordów. Ten sam identyfikator z innym payloadem
zwraca 409. Formularz zachowuje identyfikator przy ponowieniu po błędzie sieci
do momentu zmiany danych lub zamknięcia/odświeżenia strony. Klient LLM powinien
zachować identyfikator operacji aż do potwierdzenia wyniku.

Typ relacji opisuje, kim jest `related_contact_id` dla `contact_id`.
Przykładowo rodzic → dziecko ma typ `dziecko`. Wystarcza jeden wiersz:
widok kontaktu pokazuje oba kierunki. Bliźnięta również łączy jeden wiersz.

## Wdrożenie

Wdrożenie wymaga backendu i frontendu z tymi zmianami oraz migracji:

- `e93b71d6a204`: metadane opisów, przeniesienie istniejących kluczy zdjęć
  do nowej tabeli i klucz obcy. Nie pobiera ani nie przenosi plików.
  Następuje po migracjach miniatur, wydarzeń grup i prywatnych dokumentów
  (`108d63e61a8f`) z równoległej pracy nad kontaktami.
- `f04c82e7b315`: nazwy robocze, opcjonalne nazwisko i potwierdzenia operacji
  tworzenia rodziny.

Na środowisku docelowym uruchom standardową procedurę migracji Lenie
(`alembic upgrade head` w katalogu backendu) przed startem nowego backendu.
Nie jest potrzebny reimport Obsidiana ani przetwarzanie wszystkich kontaktów
przez model. Migracje nie tworzą członków rodziny kontaktu 493.

Downgrade drugiej migracji zatrzyma się, jeśli istnieją kontakty bez nazwiska:
nie wstawia za użytkownika fikcyjnych nazwisk. Przed powrotem do starej wersji
trzeba rozwiązać tę niezgodność danych.

## Panel zdjęcia i klasyfikacja

Panel **Szczegóły zdjęcia** zastępuje opis w treści karty kontaktu. Pokazuje duży
podgląd, wspólny opis użytkownika, porównanie dwóch opisów AI i listę kontaktów
współdzielących zdjęcie. Rodzina nadal korzysta z `photo.user_description`.

- `GET /contact_photos/{uuid}` zwraca obiekt zdjęcia, `photo_url` i `contacts`:
  `contact_id`, `display_name`, `uuid`, `depicts_contact`, `link_revision`, `is_current_photo`.
- `PATCH /contact_photos/{uuid}/description`: `user_description`, `user_description_revision`.
- `POST /contact_photos/{uuid}/describe`: `model` (porównanie to dwa niezależne wywołania).
- `PATCH /contact_photos/{uuid}/classification`: `subject_kind`, `people_count`, `classification_revision`.
  Temat: `people` (Ludzie), `no_people` (Bez ludzi), `unknown` (Nieustalone).
  Liczba jest nieujemną liczbą całkowitą lub null (nieustalona); dla `no_people` musi być null.
- `PATCH /contact_photos/{uuid}/contacts/{contact_id}`: `depicts_contact` (true/false/null), `revision`.
  To niezależna informacja, czy fotografia przedstawia konkretny kontakt.
- `POST /contact_photos/{uuid}/classify/suggest`: opcjonalny `model`, domyślnie
  `google/gemma-4-31B-it`. Wyłącznie jawne kliknięcie **Zaproponuj klasyfikację (AI)**
  uruchamia płatne wywołanie, z operacją `contact_photo_classification`. Wynik
  `{subject_kind, people_count}` nie jest zapisywany; trafia tylko do formularza.
  Użytkownik sprawdza propozycję i zapisuje ją osobno. Upload, opis i otwarcie
  strony nigdy nie uruchamiają klasyfikacji. Prompt zawiera jedynie pytanie
  o widoczność i liczbę ludzi, bez opisu użytkownika, nazwisk, relacji i wyników AI.

Każdy zapis sprawdza własną wersję. Przy 409 panel odświeża dane i wersje,
zachowując szkice użytkownika. Stare endpointy kontaktu pozostają adapterami
z kontrolą aktualnego `storage_key`. Zmiany opisu, wyników AI i klasyfikacji
są logowane dla wszystkich powiązanych kontaktów (także historycznych),
a zmiana `depicts_contact` tylko dla danego kontaktu. Zdjęcie bez powiązań
nie otrzymuje sztucznego właściciela ani wpisu w historii kontaktu.

`contact_photo_links` zachowuje powiązania po wymianie lub odpięciu awatara.
Scalanie kontaktów przenosi powiązania zdjęć na kontakt docelowy; przy wspólnym
zdjęciu zachowuje jego dotychczasowe oznaczenie `depicts_contact`.
Historia obejmuje te powiązania oraz starsze uploady w katalogu UUID kontaktu.
Przywrócenie dopuszcza tylko zdjęcie powiązane lub z własnego katalogu.
Migracja `b7e41c9a620d` po `a5c27d9e4b18` uzupełnia UUID istniejących zdjęć,
dodaje klasyfikację i tworzy powiązania wszystkich aktualnych awatarów.
Downgrade usuwa nowe metadane i powiązania, zachowując zdjęcia i ich opisy.
