# Pola kontaktu według kategorii (Osoba prywatna / Firma)

Prywatna książka kontaktów (`backend/library/contact_routes.py`, `backend/library/db/models.py:Contact`, frontend `web_interface_react/src/modules/shared/pages/contact.tsx`) miała pierwotnie tylko jedną kategorię kontaktów — `Osoba prywatna` — i wszystkie pola formularza były dopasowane do tego modelu. Kategoria `Firma` (dodana przy okazji kontaktu 638 „Kal - Serwis Artur Kalicki”, zob. `contact_relationships` łączące ją z właścicielem-osobą) wprowadziła kontakty, które nie są osobami: JDG, spółki, serwisy. Część pól formularza opisuje wyłącznie cechy *osoby* i nie ma odpowiednika dla *firmy* — ten dokument opisuje każde pole, po co istnieje i w której kategorii jest pokazywane.

Widoczność jest sterowana kategorią kontaktu — w kodzie frontendu to `contact.category_name !== "Firma"` (widok) / `isCompanyCategory` liczone z `form.category_id` (edycja), `contact.tsx`. Pole ukryte dla kategorii „Firma” nie jest renderowane ani w trybie odczytu, ani w formularzu edycji — jeśli istniejące dane mimo to je zawierają (np. z importu sprzed wprowadzenia kategorii), po prostu nie są pokazywane, nie są kasowane.

## Tożsamość / nazwa

| Pole | Po co istnieje | Osoba prywatna | Firma | Uzasadnienie |
|---|---|---|---|---|
| `category_id` / `category_name` | Typ kontaktu — steruje wszystkimi regułami widoczności poniżej | widoczne, edytowalne, **na samej górze formularza** | widoczne, edytowalne, **na samej górze formularza** | musi być zawsze dostępne i widoczne jako pierwsze — to od niego zależy reszta formularza. Zmiana kategorii w dowolną stronę (Firma ↔ Osoba prywatna) jest dozwolona bez ograniczeń — to zwykły select bez blokady kierunku. Zmiana **nie czyści** wartości pól, które przez to stają się ukryte (np. imię/nazwisko ustawione przy „Osoba prywatna” pozostają w rekordzie po przełączeniu na „Firma”, tylko przestają być widoczne/edytowalne) — świadomie nieniszczące zachowanie |
| `first_name`, `last_name` | Imię i nazwisko osoby | widoczne | **ukryte** | firma nie ma imienia/nazwiska; wcześniej można je było wpisać nawet przy kategorii „Firma” — błąd naprawiony |
| `display_label` | Nazwa robocza/wyświetlana, gdy imię i nazwisko są nieznane lub gdy potrzeba krótszej nazwy niż pełna | widoczne | widoczne | dla firmy przydatne jako skrócona nazwa wyświetlana (np. „Serwis Kalickiego” zamiast pełnej nazwy z CEIDG) — nie jest to pole person-specific |
| `company` | Pierwotnie: pracodawca *osoby*. Dla kategorii „Firma”: pełni rolę nazwy własnej kontaktu | widoczne | widoczne | dla „Firma” to pole niesie nazwę firmy — świadome przeciążenie semantyczne (patrz sekcja „Znane kompromisy”) |
| `gender` | Płeć — pomocna przy rozpoznawaniu obcych imion bez zdjęcia | widoczne | **ukryte** | cecha wyłącznie osoby |

## Dane kontaktowe i adres

| Pole | Po co istnieje | Osoba prywatna | Firma | Uzasadnienie |
|---|---|---|---|---|
| `phone_numbers`, `email_addresses` (+ starsze `phone_number`/`email`) | Kanały kontaktu | widoczne | widoczne | uniwersalne — firma/JDG ma własny telefon/e-mail tak samo jak osoba |
| Adresy (`Address`/`ContactAddress`, sekcja „Adresy”) | Adres kontaktowy/wizytowy — od 2026-09-20 model współdzielony i strukturalny (ulica/nr/kod/miasto/kraj), z geokodowaniem i weryfikacją rejestrową; zob. [`docs/contact-address-external-services.md`](contact-address-external-services.md) | widoczne | widoczne | sensowny dla obu; dla firmy to inny adres niż rejestrowy z `contact_organizations.address` (ten drugi opisuje adres z CEIDG konkretnej afiliacji, nie ogólny adres kontaktowy) |
| `position` | Stanowisko *osoby* w organizacji | widoczne | **ukryte** | rola osoby, firma nie ma „stanowiska” |
| `current_city` | Miasto zamieszkania — motyw do small talku | widoczne | **ukryte** | pole small-talkowe, z natury osobowe |
| `hometown` | Miasto pochodzenia — motyw do small talku | widoczne | **ukryte** | jak wyżej |

## Cechy osobiste

| Pole | Po co istnieje | Osoba prywatna | Firma | Uzasadnienie |
|---|---|---|---|---|
| `birthday`, `birthday_month`/`birthday_day` | Data urodzin (pełna lub bez roku, np. z Facebooka); zasila widok „Nadchodzące urodziny" (`GET /contacts/upcoming_birthdays`) | widoczne jako „Urodziny” | widoczne, **przemianowane na „Data założenia”** | mechanizm jest w istocie ogólnym „przypomnieniem o rocznicy”, nie stricte urodzinami osoby — backend (`contact_birthdays.py`) jest w pełni generyczny (liczy `turning_age`/`next_occurrence` bez odwołania do kategorii, a etykieta „kończy N lat” brzmi naturalnie i dla rocznicy firmy), więc zamiast ukrywać pole, etykieta w UI (edycja i widok, `contact.tsx`) zmienia się warunkowo na „Data założenia” dla `category_name === "Firma"` — ta sama kolumna, inny opis |
| `nationality` | Narodowość osoby | widoczne | **ukryte** | cecha osobista/etniczna; dla firmy odpowiednikiem byłby kraj rejestracji, ale to inny koncept — NIP/REGON już są w `contact_organizations` |
| `languages` | Znajomość języków przez osobę | widoczne | **ukryte** | kompetencja osoby, nie firmy |
| Zainteresowania / Wykształcenie (`ContactInterestsEducation`, tabele `contact_interests`/`contact_education`) | Hobby i wykształcenie osoby | widoczne | **ukryte** | jednoznacznie osobowe |
| Profil WhatsApp (`whatsapp_profile`, sekcja „Profil sąsiedzki”) | Fakty o osobie wyekstrahowane automatycznie z czatów WhatsApp | widoczne (gdy istnieje) | **ukryte** | analiza dotyczy prywatnych rozmów z konkretną osobą; firma/JDG nie ma takiego profilu |

## Organizacje i relacje

| Pole | Po co istnieje | Osoba prywatna | Firma | Uzasadnienie |
|---|---|---|---|---|
| Organizacje (`contact_organizations` — etat/JDG/funkcje) | Afiliacje *osoby* wobec innych podmiotów (może mieć kilka naraz: etat + własna JDG) | widoczne | **ukryte** | opisuje przynależność osoby do organizacji; kontakt-firma nie ma „własnych” afiliacji w tym sensie — dane JDG samej firmy (NIP/REGON z CEIDG) siedzą w tej tabeli przy kontakcie **osoby-właściciela**, nie przy kontakcie-firmie |
| Relacje (`contact_relationships`) | Powiązania między dowolnymi dwoma kontaktami (rodzina, znajomi, pracownik–pracodawca, **właściciel firmy**) | widoczne | **widoczne — kluczowe** | to właśnie tym mechanizmem kontakt-firma jest połączony z osobą, np. `Artur Kalicki (127) --właściciel--> Kal - Serwis Artur Kalicki (638)`; ukrycie zerwałoby jedyny widoczny link między nimi |
| Linki (`contact_links` — LinkedIn/Facebook/WWW) | Profile społecznościowe/strona | widoczne | **widoczne** | istotne również dla firmy — strona WWW, profil FB firmy to naturalne dane kontaktowe |
| Grupy (`contact_groups`) | Ręczne grupowanie kontaktów (np. „Rodzina”, „Tuwima Gardens”) | widoczne | widoczne | użyteczne też dla firm (np. grupa „usługodawcy”) |
| Wydarzenia (`contact_group_events`) | Wydarzenia życiowe/grupowe z udziałem kontaktu | widoczne | widoczne | rzadki przypadek dla firmy, ale nieszkodliwy — nie ukrywane |

## Pola uniwersalne (bez zmian dla żadnej kategorii)

| Pole | Uzasadnienie |
|---|---|
| `notes`, `private_notes` | wolny tekst, sensowny dla dowolnego typu kontaktu |
| `is_archived` | status archiwizacji — uniwersalny |
| Zdjęcie (`contact_photos`) | traktowane elastycznie jako portret osoby albo logo/zdjęcie firmy — model danych nie ma nic person-specific poza opisową etykietą UI |
| Historia zmian (`contact_change_log`) | audyt tylko do odczytu, uniwersalny |
| `pesel` | numer PESEL — pole istnieje w modelu i etykietach audytu, ale **nie ma edytowalnego wejścia w formularzu** (ustawiane tylko przez import); z natury dotyczyłoby wyłącznie osób, gdyby kiedyś trafiło do formularza |

## Znane kompromisy

- **`company` jako nazwa własna firmy.** Pole `Contact.company` pierwotnie oznaczało „pracodawca tej osoby”. Dla kategorii „Firma” używamy go jako nazwę samego kontaktu (fallback w `contact_display_name()`, `backend/library/contact_names.py`: imię+nazwisko → nazwa robocza → `company` → „Kontakt {id}”). Działa, ale jeśli kiedyś powstanie osobna tabela `companies`, to pole jest kandydatem do wydzielenia.
- **Adres firmy w dwóch miejscach.** `Contact.address` (ogólny adres kontaktowy) i `ContactOrganization.address`/`correspondence_address` (adres rejestrowy/do doręczeń konkretnej afiliacji z CEIDG) mogą się pokrywać dla kontaktu-firmy, ale to świadomie odrębne pola o różnym pochodzeniu danych — jedno wpisywane ręcznie, drugie z rejestru.
- **Brak wymuszenia w bazie.** Ukrywanie pól po kategorii dzieje się wyłącznie w warstwie UI (`contact.tsx`). Backend (`validate_contact_name`, `_contact_dict`) nie blokuje zapisania np. `gender` przy kategorii „Firma” przez bezpośrednie wywołanie API — to świadomy wybór (kategorie są otwartym słownikiem zarządzanym z UI, nie sztywnym enumem), więc walidacja na tym poziomie byłaby krucha.
