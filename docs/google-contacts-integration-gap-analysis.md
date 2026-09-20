# Google Contacts a książka kontaktów Lenie

Analiza: 2026-09-19. Porównano kod `../google_contacts_integration` z bieżącym
Lenie. Statusy opisują kod w repozytorium; wykonanie migracji na NAS-ie opisano poniżej.
Nie uruchamiano starych skryptów ani nie odczytywano tokenów OAuth.

## Co wykorzystać ze starego projektu

| Element | Ocena i zastosowanie |
| --- | --- |
| `google_contacts_display.py` | Wzorzec wywołania Google People API do importu bez CSV. Wymaga paginacji, mapowania i zapisu w Lenie. |
| `api/google/api_service.py` | OAuth jest już obsługiwany w `backend/library/google_auth.py`; używać obecnego modułu z konfigurowalnymi ścieżkami i tokenem JSON. |
| `library/text_phone_number_format.py` i testy | Przykłady formatowania polskich numerów i przypadki testowe. Ręczne listy prefiksów nie powinny być podstawą ogólnej walidacji. |
| `google_contacts_update.py` | Inspiracja do późniejszego eksportu; nie przenosić bez naprawy wyboru numeru, kontroli konfliktów i obsługi błędów. |
| `google_contacts_csv_import*.py` | Zastąpione importerem Lenie, który zna obecny model, grupy, historię zmian i dry-run. Stare skrypty bazują na pozycjach kolumn i innym schemacie SQL. |

Stare skrypty importują `library.api.google.api_service`, choć plik znajduje się
w `api/google/api_service.py`. Odczyt kończy się na pierwszej stronie 500 kontaktów.
Aktualizacja numerów używa identyfikatora źródła jako identyfikatora pojedynczego
numeru: kilka pól może mieć to samo źródło. Ponadto próbuje zapisywać
`canonicalForm`, które według API jest polem tylko do odczytu.

## Lista różnic do zmniejszania

| Status | Różnica | Następny krok / kryterium ukończenia |
| --- | --- | --- |
| [x] Kod gotowy | Jeden telefon i jeden e-mail w Lenie | Listy z etykietami w modelu, migracja, API, formularz, wyszukiwanie i import CSV. Szczegóły poniżej. |
| [ ] | Brak bezpośredniego importu People API | Klient oparty na obecnym OAuth, zakres `contacts.readonly`, wszystkie strony, dry-run, mapowanie i zapis historii. |
| [ ] | Powiązanie kontaktu Google z Lenie | Wykorzystać istniejące unikalne `google_contact_resource_name`; rozstrzygać niejednoznaczne dopasowania przed przypisaniem identyfikatora. |
| [ ] | Synchronizacja przyrostowa | Przechowywanie `syncToken`, obsługa wygaśnięcia, usunięć, ponowień i zmian identyfikatorów zasobu. |
| [x] Kod gotowy | Normalizacja telefonów | Wspólny zapis E.164 i klucz porównawczy, domyślnie PL, obsługa prefiksów `+`/`00`, numerów zagranicznych i wewnętrznych. Numery usługowe i nierozpoznane zachowane, wykluczone z automatycznego dopasowania osób. |
| [~] Częściowo | Dopasowanie CSV | Wszystkie poprawne telefony uczestniczą w dopasowaniu; kolizje i sprzeczne nazwy/numery są zgłaszane bez zmiany kontaktu. Do rozważenia pozostaje dopasowanie po e-mailach. |
| [x] Kod gotowy | Urodziny bez roku | `--MM-DD` trafia do miesiąca i dnia, z obsługą 29 lutego. Konflikty nie nadpisują istniejących danych. |
| [ ] | Zdjęcia z Google | Import zdjęcia do istniejącego magazynu zdjęć, z pomijaniem awatarów domyślnych i zachowaniem zasad wyboru zdjęcia. |
| [ ] | Grupy przez API | CSV już mapuje etykiety na grupy. Dodać odpowiednik dla członkostw i nazw grup Google. |
| [ ] | Pozostałe pola | Ustalić mapowanie adresów, organizacji, linków i innych danych; model ma nadal pojedynczy adres tekstowy. |
| [ ] | Eksport Lenie → Google | Jawna lista eksportowanych pól, podgląd zmian, kontrola wersji/konfliktów. Prywatne notatki i PESEL wyłączyć z eksportu. |

Zalecana kolejność dalszych prac: jednokierunkowy import API, zdjęcia i grupy,
synchronizacja przyrostowa, na końcu eksport. Opcjonalnie rozszerzyć dopasowanie
o e-maile, z zachowaniem kontroli kolizji.

## Wiele telefonów i e-maili — kontrakt

`Contact.phone_numbers` i `Contact.email_addresses` to uporządkowane listy JSONB.
Każdy element ma `value` i opcjonalne `label`. Pierwszy element jest główny.
Dotychczasowe `phone_number` i `email` pozostają kolumnami głównej wartości dla
starszych klientów i importerów. Nie zmieniono identyfikatorów kontaktów.

Przykładowy POST/PATCH `/contacts` lub `/contacts/{id}`:

```json
{
  "phone_numbers": [
    {"value": "+48 501 234 567", "label": "prywatny"},
    {"value": "+48 502 234 567", "label": "praca"}
  ],
  "email_addresses": [
    {"value": "jan@example.com", "label": "dom"},
    {"value": "jan@firma.example", "label": "praca"}
  ]
}
```

- Przekazana lista zastępuje całą listę danego rodzaju. `[]` usuwa wszystkie
  wartości; pominięcie pola niczego nie zmienia. `null` zamiast listy jest błędem.
- Zmiana kolejności wybiera nową główną wartość. GET zwraca listy oraz stare pola.
- Starszy PATCH `phone_number` / `email` zastępuje tylko wartość główną,
  zachowując pozostałe. Wyczyszczenie głównej promuje następny wpis, jeżeli istnieje.
- Jeśli klient przesyła listę i stare pole jednocześnie, wartości główne muszą
  być zgodne po normalizacji; inaczej API zwraca 400 przed zmianą kontaktu.
- Limit: 50 wpisów na listę, telefon do 30 znaków, e-mail do 255, etykieta do 100.
  Puste wartości i duplikaty są odrzucane. Porównanie e-maili ignoruje wielkość
  liter; poprawne telefony porównywane są po normalizacji opisanej poniżej.
  Nie jest to walidacja osiągalności numeru/adresu.
- Wyszukiwanie kontaktów obejmuje wartości i etykiety obu list oraz główny e-mail.
  W zapytaniach telefonicznych ignoruje formatowanie i rozpoznaje zapis `0048`.
  Nie przeszukuje nazw kluczy JSON ani nie łączy cyfr z odrębnych wpisów.
  Lista kontaktów zachowuje dotychczasową prezentację wartości głównej; szczegóły
  pokazują wszystkie wartości. Formularz pozwala dodawać, usuwać i wybierać główną.
- Import CSV zachowuje wszystkie kolumny `Phone N - Value` / `E-mail N - Value`,
  rozdziela `:::` i przenosi `Type` do etykiety. W istniejącym kontakcie dopisuje
  brakujące wartości bez zmiany dotychczasowej głównej. Nie obcina za długich danych:
  błędny wpis przerywa import przed końcowym commitem, wymagając poprawienia CSV.
- Hooki ORM synchronizują listy i stare pola podczas insert/update. W kodzie
  przypisywać całe nowe listy, nie mutować JSON w miejscu. Jeśli oba pola zmienia
  bezpośredni kod ORM, lista ma pierwszeństwo. Surowy SQL i bulk updates omijają
  hooki: muszą aktualizować oba pola zgodnie z tym kontraktem.

## Normalizacja telefonów i import dat bez roku

Nowy kod nie wymaga kolejnej migracji schematu. Backend wymaga zależności
`phonenumberslite>=9,<10` dodanej do `pyproject.toml`. Do wdrożenia potrzebny jest
obraz backendu z tą zależnością. Nie wykonano masowej normalizacji kontaktów
na NAS-ie ani ponownego importu rzeczywistych CSV w ramach tej poprawki.

- Przy zapisie przez API/ORM i odczycie CSV poprawne numery są zamieniane na
  E.164: `501 234 567`, `+48 501-234-567`, `0048 (501) 234 567` → `+48501234567`.
  Numery bez prefiksu uznajemy za polskie tylko przy 9 cyfrach. Numer zagraniczny
  powinien mieć jawny prefiks `+` lub `00`; nie zgadujemy kraju na podstawie
  końcówki numeru ani zapisu z samym kodem kraju bez prefiksu.
- Używamy metadanych libphonenumber przez `phonenumberslite`, bez ręcznych list
  prefiksów. Wewnętrzne `wew. 12`, `x12`, `ext. 12` zapisujemy jako `ext. 12`;
  różne numery wewnętrzne pozostają odrębnymi kluczami.
- Krótkie numery (`112`), kody (`*123#`), opisy i nierozpoznane wartości zostają
  zachowane. Nie służą do automatycznego dopasowywania osób. Formatowanie starych
  danych nie blokuje dopasowania: klucze są obliczane także dla istniejących wpisów.
- CSV sprawdza wszystkie telefony obu stron. Wspólny numer kilku kontaktów,
  telefony wskazujące różne osoby, różne pełne nazwy przy tym samym telefonie,
  wieloznaczna nazwa oraz zgodna nazwa przy rozłącznych poprawnych numerach
  powodują pominięcie wiersza i ostrzeżenie z numerem wiersza CSV.
- Kolejne wiersze tego samego importu mogą dopasować nowy kontakt po poprawnym
  telefonie. Nowych kontaktów nie łączymy na podstawie samej nazwy. Tryb dry-run
  prowadzi indeks planowanych kontaktów bez zapisu do bazy.
- `--04-29` zapisuje `birthday_month=4`, `birthday_day=29`, pozostawiając rok
  nieznany. `--02-29` jest poprawne; `--02-30` i `--04-31` są pomijane z raportem.
  Pełne daty ISO nadal są importowane. Znana pełna data nie jest zastępowana;
  rok można uzupełnić, jeśli istniejący miesiąc i dzień pasują do nowej pełnej daty.
  Konflikt dat pozostawia dane bez zmian i jest liczony oddzielnie od błędnych dat.
- Historia zmian uwzględnia `birthday_month` i `birthday_day`. Dry-run używa
  odłączonych kopii danych również dla kolejnych aktualizacji urodzin w jednym CSV.

Weryfikacja poprawki: 434 testy backendu (normalizacja, import CSV w dry-run
i `--apply`, kanały kontaktowe, endpointy, urodziny, zainteresowania i edukacja).
Sześć zapytań tylko do odczytu na PostgreSQL ze sztucznymi danymi potwierdziło
różne formaty numerów, dodatkowe numery i etykiety oraz brak dopasowania po
kluczach JSON i cyfrach pochodzących z różnych wpisów. Rzeczywistych kontaktów
nie zmieniano podczas tych kontroli.

## Migracja i wdrożenie

Migracja `d8f2c4a6b901` (po `a4acf996046e`) dodaje dwie kolumny i przenosi do list
istniejące niepuste telefony/e-maile, bez zmieniania wartości głównych. Nie ma
zależności od Obsidiana ani potrzeby reimportu. Przed uruchomieniem nowego backendu
zastosować migracje zgodnie z procedurą wdrożeniową projektu.

Downgrade zachowuje główne pola, ale usuwa listy; przed nim wyeksportować dodatkowe
wartości.

Migrację wykonano na NAS-ie 2026-09-19. Baza jest na `d8f2c4a6b901`; zachowano
600 kontaktów, przeniesiono 419 niepustych telefonów i 77 adresów e-mail.
Kontrola zgodności wartości głównych z pierwszym elementem list: 0 rozbieżności.
Kopia tabeli sprzed migracji znajduje się na NAS-ie:
`/share/ContainerNew/lenie-migration-backups/contacts-before-d8f2c4a6b901-20260919.dump`.
Sama migracja nie wdraża nowej wersji backendu ani interfejsu.

Weryfikacja zmiany: 378 testów backendu (kanały, endpointy kontaktów, urodziny,
zainteresowania i edukacja), test formularza dodawania/usuwania/wyboru głównego,
TypeScript i build Vite. Sprawdzono generowany SQL PostgreSQL i pojedynczy head
Alembic oraz wykonanie migracji na działającej bazie. Zapytanie kontrolne na
PostgreSQL potwierdziło wyszukiwanie dodatkowego telefonu, e-maila i etykiety.

## Źródła

- Kod starego projektu: `../google_contacts_integration`.
- Obecny importer: `backend/imports/google_contacts_import.py`.
- OAuth: `backend/library/google_auth.py`.
- [People API: listowanie i synchronizacja](https://developers.google.com/people/api/rest/v1/people.connections/list).
- [People API: model danych, PhoneNumber i Source](https://developers.google.com/people/api/rest/v1/people).
- [People API: aktualizacja kontaktu](https://developers.google.com/people/api/rest/v1/people/updateContact).
- [python-phonenumbers: parsowanie, walidacja i format E.164](https://github.com/daviddrysdale/python-phonenumbers).

Dokumentacja Google sprawdzona podczas analizy 2026-09-19. Tokeny synchronizacji
wygasają po 7 dniach; obsługa ponownego pełnego odczytu będzie częścią przyszłej
synchronizacji, a nie obecnej zmiany modelu.
