"""Closed, shared vocabulary; no database or provider dependencies."""

PO = ("person", "organization")
PP = ("person", "person")
OO = ("organization", "organization")
PC = ("person", "country")
OC = ("organization", "country")

# code: forward label, inverse label, allowed endpoint pairs
VOCABULARY = {
    "udzialowiec": ("udziałowiec", "ma udziałowca", (PO, OO)),
    "byly_udzialowiec": ("były udziałowiec", "miała udziałowca", (PO, OO)),
    "zalozyciel": ("założyciel", "założona przez", (PO, OO)),
    "zarzad": ("członek zarządu", "członek zarządu", (PO,)),
    "byly_zarzad": ("były członek zarządu", "były członek zarządu", (PO,)),
    "rada_nadzorcza": ("członek rady nadzorczej", "członek rady nadzorczej", (PO,)),
    "pracownik": ("pracuje dla", "zatrudnia", (PO,)),
    "pelnomocnik": ("pełnomocnik", "reprezentowany przez", (PO, PP)),
    "doradca": ("doradca", "korzysta z doradztwa", (PO, PP)),
    "beneficjent": ("beneficjent rzeczywisty", "ma beneficjenta", (PO, OO)),
    "umowa": ("umowa z", "umowa z", (PO, OO)),
    "platnosc": ("płaci na rzecz", "otrzymuje płatność od", (PO, OO)),
    "partner": ("partner", "partner", (PO, PP, OO)),
    "wspolpracownik": ("współpracuje z", "współpracuje z", (PO, PP, OO)),
    "inna": ("powiązanie z", "powiązanie z", (PO, PP, OO)),
    "funkcja_publiczna": ("pełni funkcję w", "funkcję pełni", (PO, PC)),
    "obywatel": ("obywatel(ka)", "obywatel(ka)", (PC,)),
    "siedziba": ("ma siedzibę w / należy do", "siedziba", (OC,)),
    "czlonek": ("członek", "ma członka", (PO,)),
    "malzonek": ("małżonek", "małżonek", (PP,)),
    "partner_zyciowy": ("partner życiowy", "partner życiowy", (PP,)),
    "rodzic": ("rodzic", "dziecko", (PP,)),
    "rodzenstwo": ("rodzeństwo", "rodzeństwo", (PP,)),
    "ziec_synowa": ("zięć / synowa", "teść / teściowa", (PP,)),
    "szwagier": ("szwagier / szwagierka", "szwagier / szwagierka", (PP,)),
    "rodzina": ("rodzina", "rodzina", (PP,)),
}
SYMMETRIC = frozenset(("umowa", "partner", "wspolpracownik", "malzonek", "partner_zyciowy",
                       "rodzenstwo", "szwagier", "rodzina"))
PIPELINE_TYPES = {"osoba": "person", "organizacja": "organization", "kraj": "country"}


def allowed(relation, subject_type, object_type):
    return relation in VOCABULARY and ((subject_type, object_type) in VOCABULARY[relation][2] or
        relation in SYMMETRIC and (object_type, subject_type) in VOCABULARY[relation][2])
