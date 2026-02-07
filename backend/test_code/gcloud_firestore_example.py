from google.cloud import firestore
from pprint import pprint
import dateparser
from dotenv import load_dotenv
import os
load_dotenv()



project_id = os.environ.get("GCP_FIRESTORE_PROJECT_ID")
database = os.environ.get("GCP_FIRESTORE_DATABASE")

db = firestore.Client(project=project_id, database=database)

doc_data = {
    "link": "https://businessinsider.com.pl/technologie/donald-trump-chce-dogonic-rosje-zwrocil-sie-o-pomoc-do-swiatowego-eksperta/kg8e4vm",
    "title": "Donald Trump chce wygrać arktyczne starcie z Rosją. Prosi o pomoc światowego eksperta",
    "date_from": "19 stycznia 2026, 21:38",
    "language": "pl",
    "text_md": """
Donald Trump upiera się, że musi przejąć Grenlandię, a jego zainteresowanie regionem Arktyki skłoniło Waszyngton do zamówienia nowych lodołamaczy. Podczas gdy Rosja posiada aż 40 takich jednostek, Stany Zjednoczone mają ich zaledwie trzy. USA złożyły zamówienie u światowego eksperta — jedynego kraju na świecie, w którym zimą mogą zamarznąć wszystkie porty.

Zgodnie z prawem USA okręty marynarki wojennej i straży przybrzeżnej muszą być zbudowane w kraju, ale w tym przypadku Donald Trump odstąpił od tego wymogu ze względów bezpieczeństwa narodowego. Prezydent powołał się na "agresywną politykę militarną i ekspansję gospodarczą ze strony zagranicznych przeciwników", mając na myśli Rosję i Chiny — pisze BBC.

W sprawie okrętów, które mogą pływać po morzach pokrytych lodem, Stany Zjednoczone zwróciły się do światowego eksperta — Finlandii.

Finlandia jest niekwestionowanym światowym liderem w dziedzinie lodołamaczy. Fińskie firmy zaprojektowały 80 proc. wszystkich obecnie eksploatowanych lodołamaczy, a 60 proc. z nich zostało zbudowanych w stoczniach w Finlandii.

Kraj ten wychodzi na prowadzenie z konieczności, wyjaśnia Maunu Visuri, prezes fińskiej państwowej firmy Arctia, która zarządza flotą ośmiu lodołamaczy. "Finlandia jest jedynym krajem na świecie, w którym zimą wszystkie porty mogą zamarznąć" — mówi BBC, dodając, że 97 proc. towarów do tego kraju jest importowanych drogą morską.

Donald Trump chce wygrać arktyczną bitwę z Rosją
W najzimniejszych miesiącach lodołamacze utrzymują fińskie porty otwarte i pełnią funkcję pionierów dla dużych statków towarowych.

Trump ogłosił w październiku, że Stany Zjednoczone zamówią cztery lodołamacze z Finlandii dla Straży Przybrzeżnej USA. Kolejnych siedem jednostek ma zostać zbudowanych w USA, z wykorzystaniem fińskich projektów i wiedzy specjalistycznej.

Zmiany klimatyczne sprawiają, że Ocean Arktyczny staje się coraz bardziej żeglowny dla statków towarowych, przynajmniej jeśli lodołamacze będą przewodzić w tym procesie, torując sobie drogę. Otwiera to szlaki handlowe z Azji do Europy, albo nad Rosją, albo na północ od Alaski i kontynentalnej Kanady, aż po Grenlandię.

Obniżony poziom lodu oznacza również, że złoża ropy naftowej i gazu pod Arktyką są bardziej dostępne. "W tej części świata jest teraz po prostu znacznie większy ruch" — mówi BBC Peter Rybski, emerytowany oficer marynarki wojennej USA i ekspert ds. lodołamaczy z Helsinek.

Finlandia buduje lodołamacze dla USA
Fińska firma Rauma Marine Constructions zbuduje dwa lodołamacze dla Straży Przybrzeżnej USA w swojej stoczni w fińskim porcie Rauma. Dostawa pierwszego statku planowana jest na 2028 r.

Kolejne cztery zostaną zbudowane w Luizjanie, a wszystkie sześć statków zostanie zaprojektowanych przez Aker Arctic Technology we współpracy z kanadyjskim partnerem Seaspan.

Zamówienia dla USA są częścią starań o dorównanie rosyjskiej liczbie lodołamaczy. Obecnie Rosja posiada ich około 40, w tym osiem o napędzie jądrowym. Dla porównania, w USA obecnie eksploatowane są tylko trzy. Tymczasem Chiny eksploatują około pięciu jednostek zdolnych do żeglugi polarnej.

Źródło: BBC        
    """

}

document_id = 1

doc_ref = db.collection("articles").document(str(document_id))
snapshot = doc_ref.get()

if snapshot.exists:
    print("OK: Dokument znaleziony!")
    data = snapshot.to_dict()
    created_at = data["created_at"]

    if created_at is None:
        print("Pole created_at nie istnieje w dokumencie")
    else:
        print(f"Wartosc pola: {created_at}")
        print(f"Typ danych w Pythonie: {type(created_at)}")
        created_at_type = type(created_at)
        pprint(created_at_type)

        if isinstance(created_at, str):
            print("To jest STRING.")
            created_at_datetime = dateparser.parse(created_at)
            print(f"To jest datetime: {created_at_datetime}")

            # Aktualizacja tylko jednego pola
            doc_ref.update({
                "created_at": created_at_datetime
            })
            print("Pole created_at zostało zaktualizowane do formatu Timestamp.")

        elif hasattr(created_at,
                     'nanosecond'):  # Timestampy Firestore mapują się na datetime (z biblioteki datetime lub google.api_core.datetime_helpers)
            print("To jest DATE / TIMESTAMP.")

else:
    print("ERROR: Nie ma takiego dokumentu!")
    print("Tworze")
    db.collection("articles").document(str(document_id)).set(doc_data)
