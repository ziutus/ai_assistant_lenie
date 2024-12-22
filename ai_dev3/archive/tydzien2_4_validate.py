from dotenv import load_dotenv
load_dotenv()

from library.ai import ai_ask

robo_data = """
REPAIR NOTE FROM: Repair department Godzina I3:30. Przeprowadzono aktualizacje modulu AI analizujacego ruchu. 
wzorce Wprowadzono dodatkowe algorytmy umožliwiajace szybsze przetwarzanie i bardziej precyzyjna analize zachowan niepozadanych. 
Aktualizacja zakonczona sukcesem, wydajnosc systemu wzrosla o I8%, со potwierdzaja pierwsze testy operacyjne. 
Algorytmy dzialaja W pelnym zakresie APPROVED BY Joseph N. 
"""

ai_task = f"""
Poniższy tekst zawiera dane z pewnej gry. Opis dotyczy fabryki i ochrony tej fabryki. Przypisz go do jednej z kategorii:
 * jeżeli tekst opisuje schwytanie czyli pojmanie ludzi lub o śladach ich obecności, przypis do kategorii "people", Nie przypis tej do kategorii, gdy opisywane jest samopoczucie zespołu patrolowego.
 * jeżeli tekst opisuje usterki hardware, przypis do kategorii "hardware", nie przypisuj notatek związanych z software ani aktualizacją algorytmów
 * pozostałe teksty przypisuj do kategorii "others".
 
Wyjaśnij swoje rozumowanie

text: {robo_data}.
"""

ai_answer = ai_ask(ai_task, model="gpt-4o", temperature=0.0)

print("\n\n")
print(f"AI answer: {ai_answer.response_text}")
