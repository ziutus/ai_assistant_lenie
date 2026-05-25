
site_rules = {
    "https://wiadomosci.wp.pl/": {
        "remove_before": ["PomorskieWrocławKoronawirus", "PomorskieWrocławKoronawirus"],
        "remove_after": [r"Elementem\swspółczesnej\swojny\sjest\swojna\sinformacyjna",
                             r"Masz newsa,\s+zdjęcie\s+lub\s+filmik\?\s+Prześlij\s+nam\s+przez\s+dziejesie\.wp\.pl\s+Oceń\s+jakość\s+naszego\s+artykułu",# noqa
                         r"### Wybrane dla Ciebie",# noqa
                         r"PREMIUM\s+Zapisz\s+się\s+na\s+newsletter!"# noqa
        ], # noqa
        "remove_string": ["Wyłączono komentarze", "Dalsza część artykułu pod materiałem wideo"],# noqa
        "remove_string_regexp": [r"\n\s*Trwa\sładowanie\swpisu:\sfacebook\s*\n", r"\n\s*Rozwin\s*\n"] # noqa
    },
    "https://wydarzenia.interia.pl": {
        "remove_before": [
            r'Lubię to\d+Super\d+Hahaha\d+Szok\d+Smutny\d+Zły\d+Lubię toSuper\d+Udostępnij',
            r"Pogoda\s+na\s+\d+\s+godzinPogoda\s+na\s+\d+\s+dni",
            r'Dzisiaj, \d{1,2} \w+ \(\d{2}:\d{2}\)\nLubię to\n\d+'
        ],
        "remove_after": [
            r'Zobacz takżePolecaneDziś w InteriiRekomendacjeNapisz',
            r"Lubię toLubię to\d+Super\d+Hahaha\d+Szok\d+Smutny\d+Zły\d+",
            r"Bądź na bieżąco i zostań jednym z 200 tys. obserwujących nasz fanpage",
            r"Bądź na bieżąco i zostań jednym z ponad 200 tys. obserwujących nasz fanpage",
            r"Zobacz również:"
        ],
        "remove_string": [],
        "remove_string_regexp": [
        r"Lubię toLubię to\d+Super\d+Hahaha\d+Szok\d+Smutny\d+Zły\d+Lubię toSuper(\d+|\d+,\d tys.)Udostępnij", r"REKLAMA\n", r"Treść zewnętrzna\n"] # noqa
    }, # noqa
    "https://wiadomosci.onet.pl/": {
        "remove_before": [r"min\s+czytania\s+FACEBOOK\s+X\s+E-MAIL\s+KOPIUJ\s+LINK"],
        "remove_after": [r"Cieszymy\ssię,\sże\sjesteś\sz\snami.\sZapisz\ssię\sna\snewsletter\sOnetu"],
        "remove_string": [],
        "remove_string_regexp": []
    },
    "https://www.onet.pl/informacje/newsweek": {
        "remove_before": [r"PremiumNewsweekŚwiat", r"PremiumNewsweekPsychologia", r'\b([0-2]?[0-9]|3[0-1]) (stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia) (\d{4}), ([0-1]?[0-9]|2[0-3]):([0-5][0-9])\b,\s(\d+)\nLubię to'],
        "remove_after": [],
        "remove_string": [],
        "remove_string_regexp": [
            r"Tekst\sopublikowany\sw\samerykańskiej\sedycji\s\"Newsweeka\".",
            r"Tytuł,\slead\si\sskróty\sod\sredakcji\s\"Newsweek\sPolska\""
        ]
    },
    "https://www.onet.pl/styl-zycia/newsweek": {
        "remove_before": [r'\b([0-2]?[0-9]|3[0-1]) (stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia) (\d{4}), ([0-1]?[0-9]|2[0-3]):([0-5][0-9])\b,\s(\d+)\nLubię to', r'(\d+)\smin\sczytania'],
        "remove_after": [r"Dziękujemy, że przeczytałaś/eś nasz artykuł do końca. Subskrybuj Onet Premium."],
        "remove_string": ["Dalszy ciąg materiału pod wideo"],
        "remove_string_regexp": []
    },
    "https://www.onet.pl/informacje/": {
        "remove_before": [r"ięcej\stakich\shistorii\sznajdziesz\sna\sstronie\sgłównej\sOnetu", r"To jest treść premium dostępna w ramach pakietu", r'Lubię to'],
        "remove_after": [r"Dziękujemy,\sże\sprzeczytałaś/eś\snasz\sartykuł\sdo\skońca"],
        "remove_string": ["reklamareklama", "Rozmowę można także obejrzeć w formie wideo:"],
        "remove_string_regexp": [r"reklama\s*\n"]
    },
    "https://www.onet.pl/technologie/": {
        "remove_before": [r"To jest treść premium dostępna w ramach pakietu"],
        "remove_after": ["Dziękujemy, że przeczytałaś/eś nasz artykuł do końca. Subskrybuj Onet Premium. Bądź na bieżąco! Obserwuj nas w Wiadomościach Google."],
        "remove_string": [],
        "remove_string_regexp": []
    },
    "https://businessinsider.com.pl/": {
        "remove_before": [r"min\sczytania\s+Udostępnij\sartykuł"],
        "remove_after": [r"Dziękujemy,\sże\sprzeczytałaś/eś\snasz\sartykuł\sdo\skońca"],
        "remove_string": [],
        "remove_string_regexp": []
    },
    "https://biznesalert.pl/": {
        "remove_before": ["AUTOR"],
        "remove_after": ["WARTO PRZECZYTAĆ"],
        "remove_string": [],
        "remove_string_regexp": []
    },
    "https://zielona.interia.pl": {
        "remove_before": [r'Dzisiaj,\s+\d{2}:\d{2}\nLubię to\n\d+\nUdostępnij\n'],
        "remove_after": [],
        "remove_string": [],
        "remove_string_regexp": [r'Zobacz również:\n.*?\n\n']
    },
    # "": {
    #     "remove_before" : [],
    #     "remove_after" : [],
    #     "remove_string" : [],
    #     "remove_string_regexp" : []
    # },
    "https://www.money.pl": {
        "remove_before": [r"\[Wróć na\]\(https://www\.wp\.pl/\)"],
        "remove_after": [r"Oceń jakość naszego artykułu:Twoja opinia pozwala nam tworzyć lepsze treści"],
        "remove_string": [],
        "remove_string_regexp": []
    },

}
