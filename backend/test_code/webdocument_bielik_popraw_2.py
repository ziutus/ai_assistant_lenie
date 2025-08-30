from library.ai import ai_ask
from library.stalker_web_document_db import StalkerWebDocumentDB
from dotenv import load_dotenv


load_dotenv()


# print(web_doc.text)
prompt = f"""
    Popraw interpunkcję i składnę tekstu poniżej:

Rosja w zasadzie przegrała swoją
przyszłość na dzień dzisiejszy mieli
bardzo wiele patologii w państwie ale te
patologie na skutek wojny się jeszcze
bardziej Pogłębił na w każdej z
płaszczyzn demograficznej ekonomicznej
finansowej gospodarczy
energetycznej rynku pracy sektor
prywatny upada w tej chwili Więc jeśli
My chcemy grać twardo z Rosjanami to
dzisiaj a nie wtedy kiedy oni odniosą
sukcesy i będą mogli odrobić straty
Chińczycy W mojej ocenie dostają te
sankcje już Amerykanie odcinają
technologii a oni tak zaciskają zę do
wytrzymamy to Wytrzymamy jeszcze tam
pogrz imy przy Tajwanie ale ale
wytrzymujemy bo nie ma co nie ma co iść
na wojnę totalną z amerykanami bo po
prostu nie damy rady Niemcy są
uniezależnienie energetycznie od Rosjan
jaka to była dla nas niekorzystna
sytuacja w której Rosjanie mogli
dyktować warunki Niemcom którzy liderow
Unii Europejskiej czyli Zobaczmy Jaki to
był mechanizm sterowania prawda Ukraina
która była sojusznikiem Rosji w zasadzie
przez dużą część historii stała się
jednoznacznym wrogiem i to się szybko
nie zmieni A to oznacza że Ukraina nie
może być równocześnie wrogiem Polski jak
bywało w przeszłości ucieszył się z
wyboru Donalda trumpa
[Muzyka]    """

print(len(prompt))

result = ai_ask(query=prompt, model="Bielik-11B-v2.3-Instruct", max_token_count=200000)

print(result.response_text)



exit(0)
