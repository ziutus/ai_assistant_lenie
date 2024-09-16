remove_before = {
    "https://wiadomosci.wp.pl/": ["PomorskieWrocławKoronawirus", "PomorskieWrocławKoronawirus"],
    "https://wydarzenia.interia.pl": [r'Lubię to\d+Super\d+Hahaha\d+Szok\d+Smutny\d+Zły\d+Lubię toSuper\d+Udostępnij',
                                      r"Pogoda\s+na\s+\d+\s+godzinPogoda\s+na\s+\d+\s+dni",
                                      r'Dzisiaj, \d{1,2} \w+ \(\d{2}:\d{2}\)\nLubię to\n\d+'],
    "https://wiadomosci.onet.pl/": [r"min\s+czytania\s+FACEBOOK\s+X\s+E-MAIL\s+KOPIUJ\s+LINK"],
    "https://www.onet.pl/informacje/newsweek": [r"PremiumNewsweekŚwiat", r"PremiumNewsweekPsychologia", r'\b([0-2]?[0-9]|3[0-1]) (stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia) (\d{4}), ([0-1]?[0-9]|2[0-3]):([0-5][0-9])\b,\s(\d+)\nLubię to'],
    "https://www.onet.pl/styl-zycia/newsweek": [r'\b([0-2]?[0-9]|3[0-1]) (stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia) (\d{4}), ([0-1]?[0-9]|2[0-3]):([0-5][0-9])\b,\s(\d+)\nLubię to'],
    "https://www.onet.pl/informacje/": [r"ięcej\stakich\shistorii\sznajdziesz\sna\sstronie\sgłównej\sOnetu", r"To jest treść premium dostępna w ramach pakietu"],
    "https://www.onet.pl/technologie/": [r"To jest treść premium dostępna w ramach pakietu"],
    "https://businessinsider.com.pl/": [r"min\sczytania\s+Udostępnij\sartykuł"]
}

remove_after = {
    "wiadomosci.wp.pl/": [r"Elementem\swspółczesnej\swojny\sjest\swojna\sinformacyjna",
                             r"Masz newsa,\s+zdjęcie\s+lub\s+filmik\?\s+Prześlij\s+nam\s+przez\s+dziejesie\.wp\.pl\s+Oceń\s+jakość\s+naszego\s+artykułu"  # noqa
                         ],
    "https://wydarzenia.interia.pl": [r'Zobacz takżePolecaneDziś w InteriiRekomendacjeNapisz',
                                      r"Lubię toLubię to\d+Super\d+Hahaha\d+Szok\d+Smutny\d+Zły\d+",
                                      r"Bądź na bieżąco i zostań jednym z 200 tys. obserwujących nasz fanpage",
                                      r"Bądź na bieżąco i zostań jednym z ponad 200 tys. obserwujących nasz fanpage",
                                      r"Zobacz również:"
                                      ],
    "https://wiadomosci.onet.pl/": [r"Cieszymy\ssię,\sże\sjesteś\sz\snami.\sZapisz\ssię\sna\snewsletter\sOnetu"],
    "https://www.onet.pl/informacje/": [r"Dziękujemy,\sże\sprzeczytałaś/eś\snasz\sartykuł\sdo\skońca"],
    "https://businessinsider.com.pl/": [r"Dziękujemy,\sże\sprzeczytałaś/eś\snasz\sartykuł\sdo\skońca"],
    "https://www.onet.pl/styl-zycia/newsweek/": [r"Dziękujemy, że przeczytałaś/eś nasz artykuł do końca. Subskrybuj Onet Premium."],
    "https://www.onet.pl/technologie/": ["Dziękujemy, że przeczytałaś/eś nasz artykuł do końca. Subskrybuj Onet Premium. Bądź na bieżąco! Obserwuj nas w Wiadomościach Google."]

}

remove_string = {
    "https://wiadomosci.wp.pl/": ["Wyłączono komentarze", "Dalsza część artykułu pod materiałem wideo"],
    "https://wydarzenia.interia.pl": [],
    "https://wiadomosci.onet.pl/": [],
    "https://www.onet.pl/informacje/": ["reklamareklama", "Rozmowę można także obejrzeć w formie wideo:"]
}

remove_string_regexp = {
    "https://wydarzenia.interia.pl": [
        r"Lubię toLubię to\d+Super\d+Hahaha\d+Szok\d+Smutny\d+Zły\d+Lubię toSuper(\d+|\d+,\d tys.)Udostępnij", r"REKLAMA\n", r"Treść zewnętrzna\n"],
    "https://wiadomosci.onet.pl/": [],
    "wiadomosci.wp.pl/": [r"\n\s*Trwa\sładowanie\swpisu:\sfacebook\s*\n", r"\n\s*Rozwin\s*\n"],
    "https://www.onet.pl/informacje/newsweek": [r"Tekst\sopublikowany\sw\samerykańskiej\sedycji\s\"Newsweeka\".",
                                                r"Tytuł,\slead\si\sskróty\sod\sredakcji\s\"Newsweek\sPolska\""],
    "https://www.onet.pl/informacje/": [r"reklama\s*\n"]
}
