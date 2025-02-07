from library.ai import ai_ask
from library.stalker_web_document_db import StalkerWebDocumentDB
from dotenv import load_dotenv

load_dotenv()

with open("tmp/markdown_output/6713_manual.md", encoding="utf-8") as file:
    text_md = file.read()

print(text_md)



prompt = f"""
Poniżej znajduje się wywiad dziennikarza i jego gościa.
Spróbuj pobrać z tekstu imię i nazwisko dziennikarza oraz gościa.
Jeżeli jest dostępny opis osoby dziennikarza i gościa, pobierz go także.
Wskaż fragment tekstu opisujący osoby.
Format odpowiedzi to json.
Przykładowy wywiad:

Jan Kowalski: Czy dobrze pracuje się panu w firmie: 'Najlepsza firma'?
Paweł Łukasicz: Świetnie, codziennie czytam gazetki i jest fajnie...

* Jak Kowalski to dziennikarz piszący w samaprawdda.pl, co rano prowadzi audycje 'porranna wódeczka' w telewizji real.tv.
* Paweł Łukasicz został zatrudniony na etacie w 'Najlepsza firma' w 1997 roku i do teraz tam pracuje.

Przykładowa odpowiedz:
{{"dziennikarz": {{
    "imie": "Jan",
    "nazwisko": "Kowalski",
    "notka_biograficzna": "Dziennikarz portalu samaprawda.pl, prowadzi audycje 'poranna wódeczka' w real.tv",
    "fragment": "Jak Kowalski to dziennikarz piszący w samaprawdda.pl, co rano prowadzi audycje 'porranna wódeczka' w telewizji real.tv."
    }}
  "gosc": {{
    "Imie": "Paweł",
    "Nazwisko": "Łukasicz"
    "notka_biograficzna": "Paweł Łukasicz to dyrektor prywatnej firmy 'Najlepsza firma' od 1997 roku.",
    "fragment": "Paweł Łukasicz został zatrudniony na etacie w 'Najlepsza firma' w 1997 roku i do teraz tam pracuje."
  }}    
}}

Wywiad:
{text_md}
"""



result = ai_ask(query=prompt, model="Bielik-11B-v2.3-Instruct", max_token_count=200000)
# result = ai_ask(query=prompt, model="amazon.titan-tg1-large", max_token_count=8192)
print(result.response_text)


exit(0)