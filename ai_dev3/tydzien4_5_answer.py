# from markitdown import MarkItDown
#
# md = MarkItDown()
# result = md.convert("tmp/tydzien4_5/notatnik-rafala.pdf")
# print(result.text_content)
#
# with open("tmp/tydzien4_5/notatnik-rafafa.md", "w", encoding="utf-8") as f:
#     f.write(result.text_content)
#
# image_text="""
# Wszystko zostało zaplanowane. Jestem gotowy, a Andrzej przyjdzie tutaj niebawem. Barbara mówi,
# że dobrze robię i mam się nie bać. Kolejne pokolenia mi za to wszystko podziękują. Władza robotów
# w 2238 nie nastąpi, a sztuczna inteligencja będzie tylko narzędziem w rękach ludzi, a nie na odwrót.
# To jest ważne. Wszystko mi się miesza, ale Barbara obiecała, że po wykonaniu zadania wykonamy skok
# do czasów, gdzie moje schorzenie jest w pełni uleczalne. Wróci moja dawna osobowość. Wróci normalność
# i wróci ład w mojej głowie. To wszystko jest na wyciągnięcie ręki. Muszę tylko poczekać na Andrzeja,
# a później użyć jego samochodu, aby się dostać do Lubawy koło Grudziądza. Nie jest to daleko. Mam tylko
# nadzieję, że Andrzejek będzie miał dostatecznie dużo paliwa. Tankowanie nie wchodzi w grę, bo nie mam kasy.
# """
#

import requests
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

json_data = {
    "task": "notes",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": {
        "01": "2019",
        "02": "Adam",
        "03": "Jaskinia Bajka w rezerwacie Rogóźno-Zamek",
        "04": "2024-11-12",
        "05": "Lubawa koło Grudziądza"
    }
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)