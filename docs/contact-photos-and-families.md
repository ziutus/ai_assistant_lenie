# Zdjęcia kontaktów, opisy i rodziny

## Użycie

Na karcie kontaktu ze zdjęciem:

1. Uzupełnij **Twój opis zdjęcia**, np. „To mąż i dwoje dzieci; dzieci są
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

Opisy należą do `contact_photos`, którego kluczem jest `storage_key`.
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
`ai_descriptions`. Kontakt zwraca też `display_label` i wyliczone `display_name`.

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
  Następuje po migracji miniatur `8b07952a8f81` z `main`.
- `f04c82e7b315`: nazwy robocze, opcjonalne nazwisko i potwierdzenia operacji
  tworzenia rodziny.

Na środowisku docelowym uruchom standardową procedurę migracji Lenie
(`alembic upgrade head` w katalogu backendu) przed startem nowego backendu.
Nie jest potrzebny reimport Obsidiana ani przetwarzanie wszystkich kontaktów
przez model. Migracje nie tworzą członków rodziny kontaktu 493.

Downgrade drugiej migracji zatrzyma się, jeśli istnieją kontakty bez nazwiska:
nie wstawia za użytkownika fikcyjnych nazwisk. Przed powrotem do starej wersji
trzeba rozwiązać tę niezgodność danych.
