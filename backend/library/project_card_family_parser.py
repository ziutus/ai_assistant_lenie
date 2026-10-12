"""Parse the science, toddler craft and logic card books, preserving visual order.

The pure parser accepts (text, font size, x0, y0) lines. PDF extraction splits
spans with different baselines (notably the oversized decorative quotation
mark), and list markers are aligned with their adjacent text before sorting.
Missing source content is never invented.
"""

from __future__ import annotations

import csv
import pathlib
import re
from collections import Counter

Line = tuple[str, float, float, float]
_MARKER = re.compile(r"№\s*(\d{3})")
_FOOTER = re.compile(r"^\d{3}\s*·")
_SPACED = re.compile(r"^(?:\S\s+){3,}\S$")
_NUMBER = re.compile(r"^\d{2}$")
_BULLETS = {"◆", "✦"}
_QUOTES = {"“", "”", "„", '"'}


def collapse(text: str) -> str:
    return "".join(text.split())


def _is_step(line: Line) -> bool:
    # Two-digit puzzle data (e.g. dominoes 31, 14, 85) are body text, not markers.
    return bool(_NUMBER.fullmatch(line[0])) and 22 <= line[1] <= 25 and line[2] < 90


def _join(parts: list[str]) -> str:
    result = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if result.endswith(("‐", "\u00ad")) or (result.endswith("-") and part[:1].islower()):
            result = result[:-1] + part
        else:
            result = f"{result} {part}" if result else part
    return result


def read_lines(page) -> list[Line]:
    """Read dict spans, retaining the real text baseline instead of a quote's bbox."""
    result = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            groups: list[list[dict]] = []
            for span in line["spans"]:
                if span["text"].strip() in _QUOTES:
                    continue
                if groups and abs(groups[-1][0]["origin"][1] - span["origin"][1]) < 2:
                    groups[-1].append(span)
                else:
                    groups.append([span])
            for group in groups:
                ink = [span for span in group if span["text"].strip()]
                if ink:
                    result.append(("".join(s["text"] for s in group).strip(), max(s["size"] for s in ink),
                                   min(s["bbox"][0] for s in ink), min(s["bbox"][1] for s in ink)))
    return result


def readable_headers(page) -> dict[str, str]:
    """Collapsed letter-spaced header -> readable text, with word breaks recovered from glyph gaps.

    The text layer has no word spaces in letter-spaced headers, but the gap between two words
    (~10 pt) is far larger than the tracking between two letters (~3.5 pt).
    """
    result: dict[str, str] = {}
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            ink = [char for span in line["spans"] for char in span["chars"] if char["c"].strip()]
            if len(ink) < 6 or any(char["c"].islower() for char in ink):
                continue
            gaps = [right["bbox"][0] - left["bbox"][2] for left, right in zip(ink, ink[1:])]
            tracking = sorted(gaps)[len(gaps) // 2]
            if tracking < 2.0:  # ordinary text, not a letter-spaced header
                continue
            words, word = [], ink[0]["c"]
            for gap, char in zip(gaps, ink[1:]):
                if gap > tracking * 1.8:
                    words.append(word)
                    word = ""
                word += char["c"]
            words.append(word)
            result["".join(words)] = " ".join(words)
    return result


def readable_title(header: str, titles: dict[str, str] | None) -> str | None:
    """Sentence-case readable form of a collapsed header (also for headers wrapped over two lines)."""
    if not titles:
        return None
    text = titles.get(header)
    if text is None:
        for first, first_text in titles.items():
            if header.startswith(first) and header[len(first):] in titles:
                text = f"{first_text} {titles[header[len(first):]]}"
                break
    return text.lower().capitalize() if text else None


def _visual_lines(lines: list[Line]) -> list[Line]:
    clean = [line for line in lines if line[0].strip() and line[0].strip() not in _QUOTES]
    aligned = []
    for text, size, x, y in clean:
        # Numbers and stars have a slightly lower bbox than their text (up to 3 pt).
        if text in _BULLETS or _is_step((text, size, x, y)):
            neighbours = [line for line in clean if x < line[2] < x + 100 and abs(line[3] - y) < 5
                          and line[0] not in _BULLETS]
            if neighbours:
                y = min(neighbours, key=lambda line: abs(line[3] - y))[3]
        aligned.append((text.strip(), size, x, y))
    return sorted(aligned, key=lambda line: (line[3], line[2]))


def _is_header(line: Line) -> bool:
    tokens = line[0].split()
    return (line[1] < 18 and line[0].isupper() and len(tokens) >= 3
            and sum(len(token) == 1 for token in tokens) >= len(tokens) * 0.6)


def split_sections(lines: list[Line]) -> tuple[list[Line], list[tuple[str, list[Line]]]]:
    """Separate the card's top and section bodies; merge wrapped letter-spaced titles."""
    top: list[Line] = []
    sections: list[tuple[str, list[Line]]] = []
    title_started = False
    last_header_y = -100.0
    for line in _visual_lines(lines):
        text, size, x, y = line
        if _FOOTER.match(text) or _MARKER.fullmatch(text):
            continue
        title_started = title_started or size >= 40
        if title_started and _is_header(line):
            if sections and not sections[-1][1] and y - last_header_y < 30:
                sections[-1] = (sections[-1][0] + collapse(text), [])
            else:
                sections.append((collapse(text), []))
            last_header_y = y
        elif sections:
            sections[-1][1].append(line)
        else:
            top.append(line)
    return top, sections


# Readable labels for frequent headers; unusual topic titles retain the exact
# collapsed source spelling. Role recognition always uses that collapsed spelling.
_LABELS = {collapse(title): title for title in (
    "Kluczowa wskazówka", "Kluczowa rada", "Potrzebne materiały", "Czego potrzebujesz",
    "Co będzie potrzebne", "Najpierw bezpieczeństwo", "Nauka o gęstości", "Dlaczego to działa",
    "Wariacje eksperymentu", "Eksperymentuj dalej", "Wskazówki do eksperymentu", "Pierwsze kroki",
    "Jak się bawić", "Jak grać", "Jak to działa", "Jak rozwiązać", "Rozwiązanie tajemnicy",
    "Rozwiązanie", "Rozwiązania", "Odpowiedź", "Odpowiedzi", "Zagadka", "Wyzwanie", "Scenariusz",
    "Analiza", "Dedukcja", "Wskazówki", "Ułatwiamy i utrzymujemy czystość",
)}
_LABELS = {key.upper(): value for key, value in _LABELS.items()}


def _roles(groups: dict[str, str]) -> dict[str, str]:
    return {header: role for role, headers in groups.items() for header in headers.split()}


# Exceptions verified against the complete inventories of the three source books.
# Numbered hands-on procedures are recognised structurally; prose procedures stay
# in sections (how_to_play), so their absence from numbered steps remains reviewable.
_HANDS_ON = _roles({
    "materials": """
        BEZPIECZNEMATERIAŁY BEZPIECZNEMATERIAŁYBUDOWLANE BEZPIECZNENARZĘDZIADOSTEMPLOWANIA
        BEZPIECZNEPRZEDMIOTYDOLICZENIA BEZPIECZNEPRZEDMIOTYDOROBIENIAODCISKÓW
        BEZPIECZNEPRZEDMIOTYDOSORTOWANIA BEZPIECZNEPRZEDMIOTYDOTESTOWANIA BEZPIECZNEPRZEDMIOTYDOWBIJANIA
        BEZPIECZNEWYPEŁNIENIADOBUTELEK BEZPIECZNEZNALEZISKAZNATURY COMOŻESZWYKORZYSTAĆ
        CZEGOBĘDZIESZPOTRZEBOWAĆ MATERIAŁYDOBEZPIECZNEJZABAWYWWODZIE MATERIAŁYDOPROSTYCHŁÓDEK
        MATERIAŁYDOWŁĄCZENIA MATERIAŁYDOZEBRANIA NARZĘDZIADOPUSZCZANIABANIEK NIEZBĘDNEAKCESORIA
        NIEZBĘDNERZECZYDOBUDOWYNAMIOTU POTRZEBNEBEZPIECZNEMATERIAŁY PROSTEMATERIAŁY PROSTEMATERIAŁYDODEKORACJI
        PROSTENARZĘDZIADOMODELOWANIA SIMPLE&SAFEMATERIALS ZBIERANIEMATERIAŁÓW ZBIERANIESKARBÓWNATURY
        ZBIERZBEZPIECZNEMATERIAŁY ZBIERZJADALNEKOLORY ZBIERZMATERIAŁY ZBIERZNAKRĘTKI
        ZBIERZPRZEDMIOTYWKOLORACHTĘCZY ŚRODKIBARWIĄCE ŚWIETNEMATERIAŁYDOBUDOWYFORTUZPODUSZEK
        MATERIAŁYKUCHENNEWCHŁANIAJĄCEWODĘ MATERIAŁYMAGNETYCZNEINIEMAGNETYCZNE PROSTEPRZEDMIOTYDOTESTÓW
        PRZEDMIOTYKUCHENNEDOTESTU KLINOWEPRZEDMIOTYKUCHENNE
        MATERIAŁY,KTÓRYCHBĘDZIESZPOTRZEBOWAĆ MATERIAŁY,KTÓRYCHMOŻESZPOTRZEBOWAĆ MATERIAŁY,KTÓRYCHMOŻESZUŻYĆ
    """,
    "safety": """
        BEZPIECZNEBADANIEMAGNETYZMU BEZPIECZNEEKSPERYMENTOWANIE BEZPIECZNAZABAWAMASĄPLASTYCZNĄ
        BEZPIECZNAZABAWAWMODELOWANIE BEZPIECZNEIPROSTETWORZENIE BEZPIECZNEISZYBKIEDEKOROWANIE
        BEZPIECZNEROZPOCZĘCIE SUPERVISIONANDCLEANUP PRZYGOTOWANIEPRZEZDOROSŁYCH:BEZPIECZNEIPROSTE
    """,
    "explanation": """
        BARIERATLENOWA CHEMIASTOJĄCAZAKOLORAMI CHŁODZĄCYSEKRETSOLI CIENIETOBLOKERYŚWIATŁA
        CIŚNIENIEWŻYCIUCODZIENNYM CODZIENNEPAROWANIE CZĘŚCIDŹWIGNI DOKĄDZNIKAWODA EFEKTCHŁODZENIA
        EFEKTMPEMBY–WYJAŚNIENIE ENERGIAWAKCJI FALEDŹWIĘKOWEWAKCJI FALUJĄCEODBICIA FIZYKALOTU FIZYKAWRUCHU
        GRAWITACJAJESTWSZĘDZIE GĘSTOŚĆMAZNACZENIE GŁÓWNEPYTANIE INNEMATERIAŁYKUCHENNE,KTÓRESIĘROZSZERZAJĄ
        INNYRODZAJDŹWIĘKU INTERPRETACJATWOJEGOBAROMETRU JAKAJESTRÓŻNICA JAKPOWSTAJĄCIENIE
        KLUCZOWECZYNNIKIWPŁYWAJĄCENASZYBKOŚĆ KLUCZOWEDZIAŁAJĄCESIŁY KLUCZOWEKONCEPCJE KLUCZOWEPOJĘCIA
        KLUCZOWESKŁADNIKIIICHROLA NIESAMOWITANITKAZWODY NIEWIDZIALNASIŁA NIEWIDZIALNEODPYCHANIE NIEWIDZIALNYNACISK
        PAROWANIEWOSKU PODSTAWOWAZASADA POLEMAGNETYCZNE PROSTANAUKAOKISZONEJKAPUŚCIE PROSTYPROGNOSTYKPOGODY
        PRZYKŁADYTARCIA PRZYKŁADYZŻYCIACODZIENNEGO REAKCJAMUSOWANIA ROLADROŻDŻYWPIECZENIU ROLAPODSTAWY
        ROZSZERZAJĄCYSIĘLÓD ROZWIĄZANIAKUCHENNE RÓWNIAPOCHYŁAWAKCJI SEKRETBLASKU SEKRETNYSKŁADNIK
        SEKWENCJAPICIA SEKWENCJASKOKU SIŁACIŚNIENIAATMOSFERYCZNEGO SIŁACIŚNIENIAPOWIETRZA SIŁAIKIERUNEK
        SIŁANAPIĘCIAPOWIERZCHNIOWEGO SIŁAPOWIETRZA SPOSOBYPRZEMIESZCZANIASIĘCIEPŁA STANDARDOWEWRZENIE
        TAJEMNICAPRZEPŁYWUWGÓRĘ TARCZAKWASOWA TRANSFORMACJAENERGII TRZYSTANYSKUPIENIAWODY
        WPŁYWGRAWITACJI WYBUCHNAUKI WYJĄTKOWASTRUKTURAWODY ZAKRZYWIONYTORLOTU ZASADAPRZYCIĄGANIA ZASADAWIRU
        ZASADAZACHOWANIAPĘDU ZMIANASTANÓWSKUPIENIA ZROZUMIENIEPRZEWODNICTWA ZROZUMIENIE„DLACZEGO” ZROZUMIEĆMAGNETYZM
        DELIKATNEKREACJE EKSPLORACJASENSORYCZNA FOCUSONTEXTUREANDFINEMOTOR GOTOWAPRACAPLASTYCZNA
        MOŻLIWOŚCIEDUKACYJNE NIESKOŃCZONEKULINARNEPRZYGODY ODBICIAZKOLBYKUKURYDZY ODKRYWANIEKOLORÓWDRUGORZĘDNYCH
        OGRZE OWYZWANIU PODSTAWOWYPOMYSŁ PRZEWODNIKPOKOLORACHIPOTRAWACH ROZWIJANEUMIEJĘTNOŚCI ROZWÓJUMIEJĘTNOŚCI
        SENSORYCZNAZABAWAWPRZESYPYWANIE SZTUKAPROSTYCHKSZTAŁTÓW WHYPOM-POMS WHYYOGURTPAINT
        NIEWIDZIALNYPOWRÓT:SKRAPLANIE PIEŚŃŁYŻKI CEL POWIĄZANIELICZBZCZĘŚCIAMICIAŁA
    """,
    "variants": """
        COMOŻNAWYPRÓBOWAĆ COWARTOWYPRÓBOWAĆ CZASNAEKSPERYMENTY DALSZEEKSPLORACJE
        EKSPERYMENTOWANIEZDŹWIĘKIEM EKSPERYMENTUJZDŹWIĘKIEM EKSPERYMENTYZPCHNIĘCIAMIWKUCHNI EKSPLORACJAWKUCHNI
        EKSPLORUJRÓŻNEDŹWIĘKI INNECIEKAWEPOMYSŁYNAZAŁAMANIEŚWIATŁA KREATYWNAZABAWAKOLORAMI
        POZADRZWIAMI POZAPAPIEREM POZATĄSTRONĄ POZAWODĄ:INNEZABAWYZZAMRAŻANIEM POZAŁYŻKĄ PUŚĆWODZEFANTAZJI
        WIĘCEJPRZYKLEJAJĄCEJSIĘZABAWY WIĘCEJZABAWZINERCJĄ WYPRÓBUJTEPOWIERZCHNIE WYPRÓBUJTEWARIANTY WYPRÓBUJTODALEJ
        BEYONDTHEBASICS CREATIVEAPPLICATIONIDEAS CREATIVEIDEAS HABITATIDEAS KREATYWNEROZSZERZENIA KREATYWNEWARIACJE
        KATEGORIEZABAWEKDOSORTOWANIA KOMBINACJEKSZTAŁTÓWIKOLORÓW NATURALNESTEMPLE NATURALNEŹRÓDŁAKOLORÓW
        POZARĄCZKAMI POZAŁUKIEM PROSTEAKTYWNOŚCI PROSTEBAZYKORONY PROSTEGRYZKOLORAMI PROSTEPOMYSŁYNAARANŻACJĘ
        PROSTEPOMYSŁYNAKOSZULKI PROSTEPOMYSŁYNARZEŹBY PROSTEPOMYSŁYNASUPEŁKI PROSTEPOMYSŁYNAWYPEŁNIENIE
        PROSTEPOŁĄCZENIAKOSTIUMÓW PROSTEPROJEKTYZNAKLEJKAMI ROZSZERZANIEGRY ROZSZERZENIEGRY ROZSZERZENIEZABAWY
        SZYBKIEPOMYSŁYNAPRZEBRANIA WYOBRAŹNIABEZGRANIC WŁASNESZABLONYNATURY ZABAWAWODGRYWANIERÓL
        BEZPIECZNEPOMYSŁYNAOZDOBY ŁATWEKSZTAŁTYUSZU
    """,
    "tip": """
        JAKSPRAWIĆ,BYTRZYMAŁOSIĘMOCNIEJ JAKUWIDOCZNIĆEFEKT JAKUZYSKAĆNAJLEPSZYEFEKT
        JAKUZYSKAĆNAJLEPSZYEFEKTSTATYCZNY JAKWZMOCNIĆBRZĘCZENIE JAKZROBIĆJESZCZEZIMNIEJ POMOCNEWSKAZÓWKI
        POMYŚLOTYM PRZYSPIESZANIE(LUBSPOWALNIANIE)PROCESU ROZWIĄZYWANIEPROBLEMÓWZGLUTKIEM SPRZĄTANIE
        SUPERWSKAZÓWKIDOTYCZĄCEELEKTRYCZNOŚCISTATYCZNEJ SUPERWSKAZÓWKINAUKOWE TWORZENIELEPSZYCHECH
        ZACHOWANIEUCZCIWOŚCIEKSPERYMENTU ZADBAJOSPRAWIEDLIWOŚĆ ZADBAJOUCZCIWOŚĆ ZAPEWNIENIEUCZCIWYCHWARUNKÓW
        ZWIĘKSZANIESTABILNOŚCI BUDOWANIENASUKCESIE JAKBUDOWAĆWYŻSZEWIEŻE JAKDOSTOSOWAĆDOMALUCHÓW
        JAKDOSTOSOWAĆGRĘDOMALUCHA JAKNAJLEPIEJSIĘBAWIĆ JAKSPRAWIĆ,BYSTAŁY JAKTOUATRAKCYJNIĆ JAKULEPSZYĆZABAWĘ
        KREATYWNEWSKAZÓWKIBUDOWLANE KREATYWNEWSKAZÓWKIDOTYCZĄCEZAMKÓW NAJLEPSZEWSKAZÓWKIDLASUKCESU
        OSTATNIESZLIFY POBUDZANIEWYOBRAŹNI SKUPIENIENAEKSPLORACJI SKUPIENIENAODPOWIEDNIMWIEKU SKUPSIĘNAZABAWIE
        SPRAW,BYBYŁOJESZCZEFAJNIEJ UATRAKCYJNIENIEZABAWY UŁATWLUBUTRUDNIJ ZACHĘCANIEDOOPOWIADANIAHISTORII
        JAKUZYSKAĆNAJLEPSZEREZULTATY MAKINGITTODDLER-FRIENDLY
    """,
    "how_to_play": """
        DELIKATNEPRZECHYLANIE DODZIEŁA EFEKTZIMNEJSZKLANKI JAKGRAĆ JAKZROBIĆFLETZESŁOMKI MUZYKAZESŁOIKÓW
        PIERWSZEKROKI POCZUJBRZĘCZENIE POCZUJWIBRACJE PROSTEEKSPERYMENTYZCIENIEM PROSTEEKSPERYMENTYZESTATYKĄ
        PROSTEEKSPERYMENTYZLUSTRAMI PROSTEKOŁOWODNE PROSTEPRZYKŁADYPRZEKAZYWANIACIEPŁA PROSTEREAKCJEKUCHENNE
        PROSTYTESTSTABILNOŚCI PRZYGOTOWANIE SPRAW,BYSIĘMIESZAŁY(TYMCZASOWO!) SPRÓBUJ SPRÓBUJTEGO
        SZYBKIEDEMONSTRACJEWKUCHNI SZYBKIEPOTRZĄSANIE TESTOWANIEPOPULARNYCHPRODUKTÓWKUCHENNYCH
        TWORZENIEZATRZAŚNIĘCIA WIELKIECHŁODZENIE WYJMOWANIEJAJKA WYPRÓBUJ WYZWANIE WYZWANIETOPNIENIA WYŚCIG
        ZABAWAMAGNETYCZNYMGLUTKIEM ZABAWAWUNOSZENIE BUDOWANIETORU BUDOWANIEZPATYCZKÓWIWŁÓCZKI
        BUDOWAPROSTEGOTEATRZYKU BUDOWASCENY DODAWANIEKOLORU DODAWANIETEKSTUR ELEMENTYTORU GETTINGSTARTED
        INSTRUKCJEUSTAWIENIA JAKSORTOWAĆ JAKSTEMPLOWAĆ JAKTOZROBIĆ KLOCKIZABAWY KRÓLEWSKIEUJAWNIENIE
        NAPĘDPODCZASZABAWY PROSTAZABAWAWUKŁADANIE PROSTEPRZYGOTOWANIE PROSTYMONTAŻ PROSTYŁUKTĘCZOWY
        PRZYGOTOWANIEDOZABAWY PRZYGOTOWANIEEKSPERYMENTU PRZYGOTOWANIEMATDLAMALUCHÓW
        PRZYGOTOWANIEPIECZĄTEKZZIEMNIAKÓW PRZYGOTOWANIESTOŁU PRZYGOTOWANIEWYKOPALISK SAFE&EASYCOLLAGE
        SPOSOBYMOCOWANIA TWORZENIEPOSTACI TWORZENIESTWORKÓW ZABAWACZASNAPARADĘ ZABAWAWFORCIE ŁATWETWORZENIEPOSTACI
        SPRAWIAMY,BYSIĘKRĘCIŁO ZBUDUJWŁASNĄŚCIEŻKĘZLICZBAMI
    """,
})

_PUZZLE = _roles({
    "solution": """
        ZWYCIĘSKIEPYTANIE PLANZWYCIĘSKI ODKODOWANAWIADOMOŚĆ ODTAJNIANIEWIADOMOŚCIZKRATKI
        OSTATECZNYPOPRAWIONYPRZYKŁADIROZWIĄZANIE POPRAWIONYPRZYKŁADIROZWIĄZANIE POPRAWNATRASA
        TWÓJKLUCZODSZYFROWANIA WYZWANIAIROZWIĄZANIA WYZWANIAIODPOWIEDZI
        ŚCIEŻKAROZWIĄZANIA PROSTYPRZYKŁADVIGENÈRE’A ĆWICZENIEDEKODOWANIA
        PRZYKŁADKODOWANIA PRZYKŁADKODOWANIA:„HI”
    """,
    "analysis": """
        BŁĘDNEOBLICZENIE CZĘSTYBŁĄD DEKODOWANIE DESZYFROWANIEPIERWSZEJWIADOMOŚCI DESZYFROWANIEWIADOMOŚCI
        DRUGIMĘDRZEC GŁĘBSZEZASTANOWIENIE JAKAJESTZASADA JAKDEDUKOWAĆ JAKDEKODOWAĆ JAKITOWZÓR
        JAKJEROZWIĄZYWAĆ JAKODSZYFROWAĆWIADOMOŚĆ JAKSIĘDOTEGOZABRAĆ JAKSIĘZANIEZABRAĆ JAKZASTOSOWAĆTRIK
        JAKZNALEŹĆMNOŻNIK JAKZNALEŹĆRÓŻNICĘCIĄGU KLUCZDOROZWIĄZANIA KROKDEDUKCJI1 KROKDEDUKCJI2
        KROKIDEKODOWANIA KROKILOGICZNE KROKIROZWIĄZYWANIA LOGIKA METODAGAUSSA
        ODSZYFROWYWANIEWIADOMOŚCI ODSZYFROWYWANIEWIADOMOŚCIWATBASZU POKRYWANIESIĘ PROCESDEDUKCJI PROSTADEDUKCJA
        PRZECIWSTAWNOŚĆ PRZYKŁAD PRZYKŁAD:KOSZYKOWOCÓW PRZYKŁAD:SUMALICZBOD1DO10 PRZYKŁADDEKODOWANIA(2SZYNY)
        PRZYKŁADKODOWANIA(2SZYNY) PRZYKŁADKODOWANIAIDEKODOWANIA
        ROZPOZNAWANIEKODUKOLORÓW ROZUMOWANIE ROZWIĄŻISPRAWDŹ ROZWÓJZAGADKI SPRAWDZANIEZAŁOŻENIA
        WYBIERZDZIAŁANIE WYPATRZLICZBY ZASTANÓWSIĘ
    """,
    "hint": """
        KLUCZOWAWSKAZÓWKADEDUKCYJNA KLUCZOWEPYTANIE KLUCZOWESTRATEGIE MYŚLOŻARÓWCE NACOZWRACAĆUWAGĘ
        NOTATKIDETEKTYWA OCOCHODZIWPYTANIU POMYŚLOPANELUSTEROWANIAWINDY PROFESJONALNEWSKAZÓWKI
        PRZYDATNEWSKAZÓWKI PUNKTYDOPRZEMYŚLENIA SKUPSIĘNAROZWIĄZANIU SZYBKIEWSKAZÓWKI
    """,
    "explanation": """
        ALFABETATBASZ COTOZNACZY„JEŚLITAK,TOCO?” CZĘSTEZASADYSEKWENCJI GŁÓWNAIDEA
        LICZBAGOŚCIAPRAWDOPODOBIEŃSTWO MATEMATYKASTOJĄCAZATYM MISTRZLUSTRZANYCHODBIĆ NIESPODZIANKA
        PRZYKŁADY PRZYKŁADYWZORÓW RODZAJEWSKAZÓWEK RODZAJEWYZWAŃ RODZAJEWZORÓW RODZAJEWZORÓWDOROZPOZNANIA
        RODZAJEWZROSTU ROZUMIENIELICZBPARZYSTYCHINIEPARZYSTYCH SIATKIPIGPEN STANDARDOWYKWADRATPOLIBIUSZA5X5
        TYPOWEWZORYWSIATKACH WIZUALIZACJAWZROSTULICZB
        ALFABETICYFRYKODUMORSE'A LITERY,KTÓREODBIJAJĄSIĘWLUSTRZE
    """,
    "how_to_play": """
        JAKJEJUŻYWAĆ KROKIDOZAKODOWANIA KROKIKODOWANIA PODSTAWOWEZASADY POTRZEBNEMATERIAŁY
        STWÓRZSWÓJALFABETSZYFRUJĄCY STWÓRZWŁASNE SZYFROWANIEWIADOMOŚCI TWORZENIESZABLONUKRATKI
        USTAWIENIESIATKIDEDUKCJI WYPRÓBUJWDOMU
        JAKUŻYWAĆKLUCZAVIGENÈRE’A
    """,
    "puzzle": """
        CEL COJESTPRAWDĄ,ACOFAŁSZEM COPOWIEDZIELI DYLEMAT ELEMENTY ETYKIETY ETYKIETYPUDEŁEK
        HIERARCHIAPIRATÓW(ODNAJSTARSZEGO) JAKIJESTCEL KILKAPIERWSZYCHPÓL KLASYCZNEWYZWANIAZZAPAŁEK
        KLASYCZNYSCENARIUSZ LISTA MIEJSCEZDARZENIA OPCJE OPCJEIWYNIKI OŚWIADCZENIA PIERWSZETROPY PODEJRZANI
        PODSTAWOWAŁAMIGŁÓWKAZSIATKĄ PRAKTYKACZYNIMISTRZA PROBLEM PRZYKŁADWYZWANIA PRZYKŁADYWYZWAŃ
        PRZYKŁADYŁAMIGŁÓWEK PRĘDKOŚCI PRĘDKOŚCIPODRÓŻNYCH PUNKTY PYTANIALOGICZNE PYTANIAQUIZOWE SEKWENCJALICZB
        SIATKA SIATKAZAMIANYSUM SORTOWANIELICZB SPRAWAZAGINIONEJZABAWKI STWIERDZENIA SZYBKIEWYZWANIAPRAKTYCZNE
        SZYFROWANESŁOWA SZYFROWANEZWROTY TERAZTWOJAKOLEJ TRUDNIEJSZELUSTRZANEZAGADKI TWÓJRUCH
        USTAWIENIE USTAWIENIESCENY WARIACJEDOROZWAŻENIA WIĘCEJZAGADEK WIĘCEJĆWICZEŃ WYPOWIEDZI
        ZAAWANSOWANESIATKI ZABAWNEWYZWANIA ZAŁOŻENIA ZWROTAKCJI ZŁAMKOD ĆWICZDESZYFROWANIE
        ĆWICZENIAWDEKODOWANIU(PRZESUNIĘCIE+3) ZNAJDŹREAKCJĘŁAŃCUCHOWĄ
    """,
    "tip": "POMYSŁYNAKARTYPRACY",
    "answer": "SPRAWDZANIEŻARÓWEK WNIOSKI NIESPODZIANKA",
})


def section_role(header: str, body: list[Line], kind: str) -> str:
    """Classify a collapsed header, using numbered layout only for hands-on steps."""
    key = header.rstrip("!?:")
    if key in {"KLUCZOWAWSKAZÓWKA", "KLUCZOWARADA"}:
        return "key_tip"
    if kind == "puzzle":
        if key == "STRATEGIAROZWIĄZANIA" and any(_is_step(line) for line in body):
            return "solution"
        if key == "PRZYKŁADOWYALFABETSZYFRUJĄCY(SŁOWOKLUCZOWE:SKARB)":
            return "solution"
        if key in _PUZZLE:
            return _PUZZLE[key]
        if "ODPOWIED" in key and not key.startswith("PODPOWIED"):
            return "answer"
        if key.startswith(("ROZWIĄZAN", "PRZYKŁADOWEROZWIĄZAN", "KROKIROZWIĄZANIA", "KROKIDOROZWIĄZANIA")):
            return "solution"
        if key.startswith(("WSKAZÓW", "PODPOWIED", "KLUCZOWEWSKAZÓW", "NAJLEPSZEWSKAZÓW")):
            return "hint"
        if key.startswith(("JAKGRAĆ", "ZASAD", "JAKKODOWAĆ", "JAKZASZYFROWAĆ", "TWORZENIEWŁAS", "KODOWANIE")):
            return "how_to_play"
        if key.startswith(("JAKROZWIĄ", "JAKTOROZWIĄ", "ROZWIĄZYWAN", "ANALIZA", "DEDUKCJA", "STRATEGI",
                           "PRZEMYŚL", "ZNAJDOWAN", "DOSTRZEGAN", "MYŚLENIE", "JAKOTYM", "KROKIDEDUKCJI")):
            return "analysis"
        if key.startswith(("ZAGAD", "WYZWAN", "SCENARIUSZ", "PRZYKŁADOW", "TWOJ", "TWOJE", "CZASNA",
                           "INNEWYZWANIE", "GŁÓWNEWYZWANIE", "ŁAMIGŁÓWKA", "KOLEJNEWYZWANIE")):
            return "puzzle"
    else:
        if key in {"CZEGOPOTRZEBUJESZ", "COBĘDZIEPOTRZEBNE", "COPOTRZEBUJESZ", "COBĘDZIESZPOTRZEBOWAĆ",
                   "BĘDZIESZPOTRZEBOWAĆ", "POTRZEBNEMATERIAŁY", "MATERIALSYOU'LLNEED", "PROSTESKŁADNIKI"}:
            return "materials"
        if _HANDS_ON.get(key) == "materials":
            return "materials"
        if any(_is_step(line) for line in body):
            return "steps"
        if key in _HANDS_ON:
            return _HANDS_ON[key]
        if "BEZPIECZEŃSTW" in key or "NADZÓR" in key or "NADZOR" in key or key == "SAFETY&FUNTIPS":
            return "safety"
        if key.startswith(("WARIACJE", "WARIANTY", "EKSPERYMENTUJDALEJ", "DALSZEEKSPERYMENTY",
                           "WSKAZÓWKIDOEKSPERYMENTU", "POMYSŁYNA", "KREATYWNEPOMYSŁY")):
            return "variants"
    if key.startswith(("DLACZEGO", "NAUKA", "CZYMJEST", "CZYMSĄ", "COTOJEST", "JAKTODZIAŁA", "JAKDZIAŁA")):
        return "explanation"
    if kind != "puzzle" and key.startswith(("MAGIA", "MAGICZNE", "WYJAŚNIENIE", "KORZYŚCI", "COSIĘDZIEJE",
                                            "COZOBACZYSZ", "COOBSERWOWAĆ", "COZAUWAŻYĆ", "OBSERW", "CODZIEJE",
                                            "COPOZOSTANIE", "COTWORZY", "COWPŁYWA", "COZOSTANIE", "TABELAOBSERWACJI")):
        return "explanation"
    if key.startswith(("WSKAZÓW", "UŁATWI", "ULEPSZ", "UCZYŃ", "DODATKOW", "JAKUATRAKCYJNIĆ",
                       "JAKUCZYNIĆ", "WIĘCEJNIŻ", "POZAPODSTAW", "TIPSFOR")):
        return "tip"
    return "other"


def _content(body: list[Line]) -> tuple[str, str | list[str]]:
    numbered = any(_is_step(line) for line in body)
    bulleted = any(line[0] in _BULLETS for line in body)
    if not numbered and not bulleted:
        return "text", _join([line[0] for line in body])
    items: list[str] = []
    current: list[str] = []
    for line in body:
        text = line[0]
        if text in _BULLETS or (numbered and _is_step(line)):
            if current:
                items.append(_join(current))
            current = []
        else:
            current.append(text)
    if current:
        items.append(_join(current))
    return "steps" if numbered else "list", items


def parse_time(text: str) -> tuple[int | None, int | None]:
    duration = re.fullmatch(r"(\d+)(?:[-–‐](\d+))?(MIN(?:UTY)?|GODZ)\.?", collapse(text), re.IGNORECASE)
    if not duration:
        return None, None
    factor = 60 if duration[3].upper() == "GODZ" else 1
    return int(duration[1]) * factor, int(duration[2] or duration[1]) * factor


_INLINE_ANSWER = re.compile(
    r"\(?\*{0,2}(?:Odpowied[zź](?:i)?|Rozwiązani[ae]|Odszyfrowana wiadomość|Oryginalna wiadomość|"
    r"Zakodowane|Szyfrogram)\s*:\*{0,2}", re.IGNORECASE,
)
# These worked examples have no answer label. Split at the observed start of
# the worked solution, retaining both the question and the original answer.
_WORKED_ANSWERS = {
    "PRZYKŁADWYZWANIA": "Wzór wydaje się polegać",
    "PRZYKŁADOWEWYZWANIE": "Jeśli Alicja mówi prawdę",
    "JAKTOROZWIĄZAĆ": "W obu przypadkach bliźniak",
}


def _puzzle_sections(role: str, title: str, fmt: str, content: str | list[str]) -> list[dict]:
    """Split explicitly labelled inline answers out of otherwise visible challenges.

    Preserve order and source wording, including parentheses/Markdown. A whole
    mixed prose suffix is hidden if it contains an answer, rather than guessing
    sentence boundaries and leaking part of the answer.
    """
    def section(part_role, part_format, part_content):
        return dict(role=part_role, title=title, format=part_format, content=part_content,
                    hidden=part_role in {"solution", "answer"})

    if role in {"solution", "answer", "key_tip"}:
        return [section(role, fmt, content)]
    items = [content] if isinstance(content, str) else content
    chunks = []
    for item in items:
        match = _INLINE_ANSWER.search(item)
        worked = _WORKED_ANSWERS.get(collapse(title).upper())
        answer_at = match.start() if match else item.find(worked) if worked else -1
        if answer_at < 0:
            parts = [(role, item)]
        else:
            parts = [(role, item[:answer_at].strip()), ("answer", item[answer_at:].strip())]
        for part_role, text in parts:
            if not text:
                continue
            if chunks and chunks[-1]["role"] == part_role and fmt != "text":
                chunks[-1]["content"].append(text)
            else:
                chunks.append(section(part_role, fmt, text if fmt == "text" else [text]))
    return chunks or [section(role, fmt, content)]


def parse_lines(lines: list[Line], *, series: str, kind: str, chapter: str = "", age_min: int | None = None,
                age_max: int | None = None, source_file: str = "", source_page: int = 1,
                titles: dict[str, str] | None = None) -> dict:
    """Build one record from positioned text lines; require the printed card marker."""
    if kind not in {"experiment", "craft", "puzzle"}:
        raise ValueError(f"Unsupported card kind: {kind}")
    markers = [match[1] for line in lines if (match := _MARKER.fullmatch(line[0].strip()))]
    if len(markers) != 1:
        raise ValueError("A card page must contain exactly one № marker")
    top, sections = split_sections(lines)
    title = _join([text for text, size, *_ in top if size >= 40])
    tagline = _join([text for text, size, *_ in top if 24.5 <= size < 30])
    description = _join([text for text, size, *_ in top if 18 <= size < 24.5])
    banner = collapse("".join(text for text, size, *_ in top if _is_header((text, size, 0, 0))))
    time_raw = next((text for text, size, *_ in top if size < 18 and not _SPACED.fullmatch(text)), "")
    time_min, time_max = parse_time(time_raw)
    card = dict(number=markers[0], series=series, kind=kind, chapter=chapter or banner.partition("·")[2],
                title=title, tagline=tagline, description=description, time_raw=time_raw,
                time_min=time_min, time_max=time_max, age_min=age_min, age_max=age_max,
                age_source="cover" if age_min is not None or age_max is not None else None,
                needs_adult=False, materials=[], tools=[], steps=[], variants=[], safety="", sections=[], flags=[],
                source_file=source_file, source_page=source_page)
    adult_text = []
    for header, body in sections:
        role = section_role(header, body, kind)
        # An analysis table has a separate answer column. Keep analysis visible,
        # but move that column (including its source title) to a hidden section.
        answer_column = next((line for line in body if line[0] == "ROZWIĄZANIE"), None)
        answers = []
        if kind == "puzzle" and answer_column:
            answers = [line[0] for line in body if line[2] >= answer_column[2] - 1 and line != answer_column]
            body = [line for line in body if line[2] < answer_column[2] - 1]
        fmt, content = _content(body)
        items = [content] if isinstance(content, str) and content else content
        if role in {"materials", "steps", "safety", "tip", "key_tip", "variants"}:
            adult_text.extend(items)
        if not content:
            card["flags"].append(f"empty_section:{role}")
        if role == "materials":
            card["materials"].extend({"qty": "", "name": item} for item in items)
        elif role in {"steps", "variants"}:
            card[role].extend(items)
        elif role == "safety":
            card["safety"] = _join([card["safety"], " ".join(items)])
        else:
            label = _LABELS.get(header.rstrip("!?:")) or readable_title(header, titles) or header
            if kind == "puzzle":
                card["sections"].extend(_puzzle_sections(role, label, fmt, content))
            else:
                card["sections"].append(dict(role=role, title=label, format=fmt, content=content, hidden=False))
        if answers:
            card["sections"].append(dict(role="solution", title="Rozwiązanie", format="list",
                                         content=answers, hidden=True))
        if role == "other":
            card["flags"].append(f"unmapped_section:{header}")
    card["needs_adult"] = "dorosł" in " ".join(adult_text).lower()
    flag_card(card)
    return card


def flag_card(card: dict) -> None:
    flags = card["flags"]
    for field in ("title", "description"):
        if not card[field]:
            flags.append(f"missing:{field}")
    if card["kind"] != "puzzle":
        for field in ("steps", "materials"):
            if not card[field]:
                flags.append(f"missing:{field}")
        if len(card["steps"]) < 2:
            flags.append("few_steps")
    elif not any(section["role"] in {"solution", "answer"} for section in card["sections"]):
        flags.append("puzzle_without_solution")
    if card["time_min"] is None:
        flags.append("time_unparsed")
    if card["title"].endswith(("‐", "-")):
        flags.append("wrapped_title_unjoined")
    card["flags"] = list(dict.fromkeys(flags))


def parse_card_pdf(path: str | pathlib.Path, *, series: str, kind: str, age_min: int | None = None,
                   age_max: int | None = None, inventory: Counter | None = None) -> list[dict]:
    """Read a book once; optionally collect (collapsed header, role) occurrence counts."""
    import fitz  # lazy: pure parser and its tests need no PDF dependencies

    path = pathlib.Path(path)
    cards = []
    chapter = ""
    with fitz.open(path) as document:
        for page_number, page in enumerate(document, 1):
            lines = read_lines(page)
            if not any(_MARKER.fullmatch(line[0]) for line in lines):
                if any(collapse(line[0]).startswith("ROZDZIAŁ") and "SEKCJA" in collapse(line[0]) for line in lines):
                    chapter = _join([text for text, size, *_ in _visual_lines(lines) if 40 <= size < 90])
                continue
            cards.append(parse_lines(lines, series=series, kind=kind, chapter=chapter, age_min=age_min,
                                     age_max=age_max, source_file=path.name, source_page=page_number,
                                     titles=readable_headers(page)))
            if inventory is not None:
                inventory.update((header, section_role(header, body, kind))
                                 for header, body in split_sections(lines)[1])
    return cards


def valid_numbering(cards: list[dict]) -> bool:
    numbers = sorted(int(card["number"]) for card in cards)
    return bool(numbers) and numbers == list(range(1, numbers[-1] + 1))


def write_review_csv(cards: list[dict], path: str | pathlib.Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["nr", "tytuł", "rozdział", "czas", "kroki", "materiały", "sekcje", "dorosły", "flagi"])
        for card in cards:
            writer.writerow([card["number"], card["title"], card["chapter"], card["time_raw"], len(card["steps"]),
                             len(card["materials"]), len(card["sections"]), card["needs_adult"],
                             " | ".join(card["flags"])])
