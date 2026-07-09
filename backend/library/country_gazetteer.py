"""Non-LLM (gazetteer-based) country detection in Polish text.

Rule-based prescreen used by extract_countries_hybrid() in article_tagging.py:
matches country-name word stems against text with Polish diacritics stripped
(via unidecode), so a single ASCII stem catches most case endings —
"ukrain*" matches Ukraina/Ukrainie/Ukrainy/ukraiński alike.

This is a candidate generator, not a topic classifier: it flags every mention
of a country name, including passing references, adjectives, and demonyms. It
deliberately over-matches (short stems can catch unrelated Polish words) since
callers are expected to filter the candidate list further — e.g. with an LLM
confirmation pass (see extract_countries_hybrid() in article_tagging.py) —
rather than treat a gazetteer hit alone as "this country is discussed".

The list of ~190 entries covers UN member/observer states plus a few widely
discussed non-UN entities (Taiwan, Kosovo). It is a closed list — country
name changes are rare, so it does not need LLM upkeep — but it IS an
approximation:
- Multi-word names (e.g. "Wielka Brytania") are matched as adjacent-word
  phrases (words may be separated by whitespace or a hyphen).
- Adjective forms with irregular stems (Niemcy/niemiecki, Włochy/włoski,
  Węgry/węgierski...) get an explicit second stem where curated; smaller
  countries only get the noun-form stem, so adjective-only mentions can be
  missed for those.
- Capitals are NOT matched (many are ambiguous — e.g. Sofia is also a first
  name, Praga is also a Warsaw district) — out of scope for this module.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from unidecode import unidecode

# name_pl, variants: each variant is a sequence of space-separated tokens; a
# token ending in "*" matches as a word stem (\bTOKEN\w*), otherwise as an
# exact word (\bTOKEN\b). Multi-token variants match adjacent words (allowing
# a hyphen between them, e.g. "Papua-Nowa Gwinea").
_COUNTRY_DATA: list[tuple[str, tuple[str, ...]]] = [
    # --- Europa ---
    ("Polska", ("polsk*",)),
    ("Niemcy", ("niemc*", "niemiec*")),
    ("Francja", ("franc*",)),
    ("Wielka Brytania", ("wielk* brytani*", "brytyj*", "zjednoczon* krolestw*")),
    ("Włochy", ("wloch*", "wlos*")),
    ("Hiszpania", ("hiszpan*",)),
    ("Portugalia", ("portugal*",)),
    ("Holandia", ("holand*", "niderland*")),
    ("Belgia", ("belgi*",)),
    ("Szwajcaria", ("szwajcar*",)),
    ("Austria", ("austri*",)),
    ("Szwecja", ("szwecj*", "szwedz*")),
    ("Norwegia", ("norweg*",)),
    ("Dania", ("dani*", "dunsk*", "dunczy*")),
    ("Finlandia", ("finland*", "fins*")),
    ("Islandia", ("island*",)),
    ("Irlandia", ("irland*",)),
    ("Grecja", ("grecj*", "greck*")),
    ("Cypr", ("cypr*",)),
    ("Malta", ("malt*",)),
    ("Czechy", ("czech*", "czesk*")),
    ("Słowacja", ("slowacj*", "slowack*")),
    ("Węgry", ("wegr*", "wegiersk*")),
    ("Rumunia", ("rumun*",)),
    ("Bułgaria", ("bulgar*",)),
    ("Chorwacja", ("chorwac*",)),
    ("Słowenia", ("sloweni*",)),
    ("Bośnia i Hercegowina", ("bosni* i hercegowin*", "bosniack*")),
    ("Serbia", ("serb*",)),
    ("Czarnogóra", ("czarnogor*",)),
    ("Macedonia Północna", ("macedoni* polnocn*", "macedonsk*")),
    ("Albania", ("alban*",)),
    ("Kosowo", ("kosow*",)),
    ("Mołdawia", ("moldaw*",)),
    ("Ukraina", ("ukrain*",)),
    ("Białoruś", ("bialorus*",)),
    ("Litwa", ("litewsk*", "litw*")),
    ("Łotwa", ("lotewsk*", "lotw*")),
    ("Estonia", ("eston*",)),
    ("Rosja", ("rosj*", "rosyj*")),
    ("Andora", ("andor*",)),
    ("Monako", ("monak*",)),
    ("San Marino", ("san marin*",)),
    ("Liechtenstein", ("liechtenstein*",)),
    ("Watykan", ("watykan*",)),
    ("Luksemburg", ("luksembur*",)),
    # --- Azja ---
    ("Chiny", ("chin*",)),
    ("Japonia", ("japon*",)),
    ("Korea Południowa", ("kore* poludniow*",)),
    ("Korea Północna", ("kore* polnocn*",)),
    ("Indie", ("indi*", "hindus*")),
    ("Pakistan", ("pakistan*",)),
    ("Bangladesz", ("banglades*",)),
    ("Sri Lanka", ("sri lank*",)),
    ("Nepal", ("nepal*",)),
    ("Bhutan", ("bhutan*",)),
    ("Malediwy", ("maldiw*",)),
    ("Afganistan", ("afganistan*", "afgansk*")),
    ("Iran", ("iran*", "iransk*")),
    ("Irak", ("irak*", "irac*")),
    ("Arabia Saudyjska", ("arabi* saudyjsk*",)),
    ("Jemen", ("jemen*",)),
    ("Oman", ("oman*",)),
    ("Zjednoczone Emiraty Arabskie", ("zjednoczon* emirat* arabski*", "emirat*")),
    ("Katar", ("katar*",)),
    ("Bahrajn", ("bahrajn*", "bahrejn*")),
    ("Kuwejt", ("kuwejt*",)),
    ("Jordania", ("jordani*",)),
    ("Liban", ("liban*",)),
    ("Syria", ("syri*", "syryjsk*")),
    ("Izrael", ("izrael*",)),
    ("Palestyna", ("palestyn*",)),
    ("Turcja", ("turcj*", "tureck*")),
    ("Gruzja", ("gruzj*", "gruzin*")),
    ("Armenia", ("armen*",)),
    ("Azerbejdżan", ("azerbejdzan*",)),
    ("Kazachstan", ("kazachstan*", "kazach*")),
    ("Uzbekistan", ("uzbekistan*", "uzbeck*")),
    ("Turkmenistan", ("turkmenistan*", "turkmen*")),
    ("Tadżykistan", ("tadzykistan*", "tadzyck*")),
    ("Kirgistan", ("kirgistan*", "kirgis*")),
    ("Mongolia", ("mongol*",)),
    ("Tajwan", ("tajwan*",)),
    ("Wietnam", ("wietnam*",)),
    ("Laos", ("laos*", "laotansk*")),
    ("Kambodża", ("kambodz*",)),
    ("Tajlandia", ("tajland*", "tajsk*")),
    ("Mjanma", ("mjanm*", "birm*")),
    ("Malezja", ("malezj*",)),
    ("Singapur", ("singapur*",)),
    ("Indonezja", ("indonezj*",)),
    ("Filipiny", ("filipin*",)),
    ("Brunei", ("brunei*",)),
    ("Timor Wschodni", ("timor* wschodni*",)),
    # --- Afryka ---
    ("Egipt", ("egipt*",)),
    ("Libia", ("libi*", "libijsk*")),
    ("Tunezja", ("tunezj*", "tunezyjsk*")),
    ("Algieria", ("algier*",)),
    ("Maroko", ("marok*", "marokansk*")),
    ("Sahara Zachodnia", ("sahar* zachodni*",)),
    ("Mauretania", ("mauretan*",)),
    ("Mali", ("mali", "malijsk*")),
    ("Niger", ("niger", "nigr*")),
    ("Nigeria", ("nigeri*", "nigeryjsk*")),
    ("Czad", ("czad*",)),
    ("Sudan", ("sudan*",)),
    ("Sudan Południowy", ("sudan* poludniow*",)),
    ("Erytrea", ("erytre*",)),
    ("Dżibuti", ("dzibut*",)),
    ("Etiopia", ("etiop*",)),
    ("Somalia", ("somal*",)),
    ("Kenia", ("keni*", "kenijsk*")),
    ("Uganda", ("ugand*",)),
    ("Tanzania", ("tanzan*",)),
    ("Rwanda", ("rwand*",)),
    ("Burundi", ("burund*",)),
    ("Demokratyczna Republika Konga", ("demokratyczn* republik* kong*", "kongijsk*")),
    ("Republika Konga", ("republik* kong*",)),
    ("Gabon", ("gabon*",)),
    ("Gwinea Równikowa", ("gwine* rownikow*",)),
    ("Kamerun", ("kamerun*",)),
    ("Republika Środkowoafrykańska", ("srodkowoafrykansk*",)),
    ("Benin", ("benin*",)),
    ("Togo", ("togo", "togijsk*")),
    ("Ghana", ("ghan*",)),
    ("Wybrzeże Kości Słoniowej", ("wybrzez* kosci sloniow*", "iworyjsk*")),
    ("Liberia", ("liberi*",)),
    ("Sierra Leone", ("sierr* leone*",)),
    ("Gwinea", ("gwine*",)),
    ("Gwinea Bissau", ("gwine* bissau*",)),
    ("Senegal", ("senegal*",)),
    ("Gambia", ("gambi*",)),
    ("Republika Zielonego Przylądka", ("zielon* przyladk*",)),
    ("Burkina Faso", ("burkin* faso*",)),
    ("Angola", ("angol*",)),
    ("Zambia", ("zambi*",)),
    ("Zimbabwe", ("zimbabwe*",)),
    ("Mozambik", ("mozambik*",)),
    ("Malawi", ("malawi", "malawijsk*")),
    ("Madagaskar", ("madagaskar*",)),
    ("Mauritius", ("mauritius*",)),
    ("Seszele", ("seszel*",)),
    ("Komory", ("komor*",)),
    ("Botswana", ("botswan*",)),
    ("Namibia", ("namibi*",)),
    ("Eswatini", ("eswatini", "suazi*")),
    ("Lesotho", ("lesotho",)),
    ("Republika Południowej Afryki", ("poludniow* afryk*", "rpa", "poludniowoafrykansk*")),
    # --- Ameryki ---
    ("Stany Zjednoczone", ("stan* zjednoczon*", "amerykansk*")),
    ("Kanada", ("kanad*",)),
    ("Meksyk", ("meksyk*",)),
    ("Gwatemala", ("gwatemal*",)),
    ("Belize", ("belize*",)),
    ("Honduras", ("hondura*",)),
    ("Salwador", ("salwador*",)),
    ("Nikaragua", ("nikaragu*",)),
    ("Kostaryka", ("kostaryk*",)),
    ("Panama", ("panam*",)),
    ("Kuba", ("kub*",)),
    ("Jamajka", ("jamajk*",)),
    ("Haiti", ("haiti", "haitansk*")),
    ("Dominikana", ("dominikan*",)),
    ("Bahamy", ("baham*",)),
    ("Barbados", ("barbados*",)),
    ("Trynidad i Tobago", ("trynidad*", "tobago*")),
    ("Antigua i Barbuda", ("antigu*", "barbud*")),
    ("Saint Kitts i Nevis", ("kitts*", "nevis*")),
    ("Dominika", ("dominik*",)),
    ("Saint Lucia", ("saint luci*", "lucia*")),
    ("Saint Vincent i Grenadyny", ("vincent*", "grenadyn*")),
    ("Grenada", ("grenad*",)),
    ("Kolumbia", ("kolumbi*",)),
    ("Wenezuela", ("wenezuel*",)),
    ("Gujana", ("gujan*",)),
    ("Surinam", ("surinam*",)),
    ("Ekwador", ("ekwador*",)),
    ("Peru", ("peru", "peruwiansk*")),
    ("Brazylia", ("brazyli*",)),
    ("Boliwia", ("boliwi*",)),
    ("Paragwaj", ("paragwaj*",)),
    ("Chile", ("chile", "chilijsk*")),
    ("Argentyna", ("argentyn*",)),
    ("Urugwaj", ("urugwaj*",)),
    # --- Oceania ---
    ("Australia", ("australi*",)),
    ("Nowa Zelandia", ("now* zeland*", "nowozelandzk*")),
    ("Papua-Nowa Gwinea", ("papu* now* gwine*",)),
    ("Fidżi", ("fidzi", "fidzyjsk*")),
    ("Wyspy Salomona", ("wysp* salomon*",)),
    ("Vanuatu", ("vanuatu*",)),
    ("Samoa", ("samoa*",)),
    ("Tonga", ("tong*",)),
    ("Kiribati", ("kiribati",)),
    ("Tuvalu", ("tuvalu*",)),
    ("Nauru", ("nauru*",)),
    ("Palau", ("palau*",)),
    ("Mikronezja", ("mikronezj*",)),
    ("Wyspy Marshalla", ("wysp* marshall*",)),
]


@dataclass(frozen=True)
class CountryEntry:
    name_pl: str
    slug: str


def _slug(name_pl: str) -> str:
    """Slug w konwencji article_tagging.extract_countries_with_llm (kraj-<slug>)."""
    ascii_name = unidecode(name_pl).lower()
    ascii_name = re.sub(r"[^a-z0-9\s-]", "", ascii_name)
    return re.sub(r"\s+", "-", ascii_name.strip())


def _compile_variant(variant: str) -> re.Pattern:
    parts = []
    for token in variant.split():
        if token.endswith("*"):
            parts.append(r"\b" + re.escape(token[:-1]) + r"\w*")
        else:
            parts.append(r"\b" + re.escape(token) + r"\b")
    return re.compile(r"[\s-]+".join(parts))


@lru_cache(maxsize=1)
def _compiled_countries() -> tuple[tuple[CountryEntry, tuple[re.Pattern, ...]], ...]:
    compiled = []
    for name_pl, variants in _COUNTRY_DATA:
        entry = CountryEntry(name_pl=name_pl, slug=_slug(name_pl))
        patterns = tuple(_compile_variant(v) for v in variants)
        compiled.append((entry, patterns))
    return tuple(compiled)


@lru_cache(maxsize=1)
def _slug_to_name_map() -> dict[str, str]:
    return {entry.slug: entry.name_pl for entry, _ in _compiled_countries()}


def slug_to_name(slug: str) -> str | None:
    """Kanoniczna polska nazwa kraju dla danego sluga (odwrotność _slug()), albo None."""
    return _slug_to_name_map().get(slug)


def detect_countries(text: str) -> list[CountryEntry]:
    """Zwróć kraje, których nazwa/przymiotnik/mieszkaniec pojawia się w tekście — bez LLM.

    Dopasowanie działa na tekście znormalizowanym (bez polskich znaków
    diakrytycznych, małe litery). To generator kandydatów, nie klasyfikator
    tematyczny — patrz docstring modułu odnośnie ograniczeń i celowego
    nadmiarowego dopasowania.
    """
    normalized = unidecode(text).lower()
    found = [entry for entry, patterns in _compiled_countries() if any(p.search(normalized) for p in patterns)]
    return sorted(found, key=lambda e: e.name_pl)
