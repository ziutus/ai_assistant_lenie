import unittest

from library.text_functions import split_text_for_embedding


text="""Ogłoszenia
 Dzień dobry Witam państwa bardzo
serdecznie jest 23 Dhul Qadah 1445 roku po hidjri albo trto Primo ma Anno
Domini bismilessimo Vigessimo quarto  Dziękuję państwu bardzo serdecznie za te
wszystkie kontakty za oferty którymi państwo składacie Ja przypomnę że w tej
chwili Poszukuję dwóch osób mam nadzieję że
znajdę albo jednej osoby która posiada dwie umiejętności Po pierwsze szukam
jakiegoś grafika ilustratora ale takie są osoby która potrafi coś narysować
odręcznie tak karykaturę nie wiem fragment komiksu postać na przykład to
by mi się bardzo bardzo przydało No jeżeli nie znajdę to będę szukał
oczywiście w internecie druga sprawa to szukam również kogoś kto mógłby
przygotować jakieś fajne elementy graficzne na przykład do szortów tak
żeby te szorty nie zaczynały się od mojej twarzy tylko żeby można było w
jakiś screen na początku włożyć jakieś drobiazgi animacyjne również do do
odcinków to chodzi Ja wiem że pań bardzo wiele osób pisze że to nie ma znaczenia
No dla części osób ma no zawsze się fajnie ogląda jeżeli ten te odcinki są
jakoś ładniej statycznie graficznie zrobione w związku z tym do tego
namawiam jak państwo być może zauważyliście co jakiś czas pojawiają
się w tej chwili już napisy w języku angielskim z tego co widzę po tych
wszystkich narzędziach statystycznych znaczenie ma to zerowe jeśli chodzi o
jakikolwiek wpływ na zasięgi prawda czy nawet na zasięgi w krajach
angielskojęzycznych znaczy czytają Polacy ze Stanów
"""

paragraph_titles = ["Ogłoszenia", "Wina Trumpa i co dalej", "Ukraina ma zgodę USA", "Iran kandydaci na prezydenta", "Liga Arabska w Pekinie", "Kroniki Bulandy - granica"]


class SplitForEmbeddingTestCase(unittest.TestCase):


    def test_hello_world(self):
        text_new = split_text_for_embedding(text, paragraph_titles)
        assert (text_new[0].find("AnnoDomini") < 0)


if __name__ == '__main__':
    unittest.main()
