import unittest
from library.lenie_markdown import remove_new_line_only_in_string


class TestRemoveNewLineOnlyInString(unittest.TestCase):
    def test_remove_new_line_only_in_string(self):
        markdown = """Rzecznik
Patela nie odpowiedział na prośbę o komentarz.

![Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21
lutego 2025 r.](https://ocdn.eu/pulscms-transforms/1/i-bk9kpTURBXy8wOGY1YzY2YWY1NjAxYjA4ZjExNzc5NTBlYzQyYWU5ZC5qcGeSlQLNA6wAwsOVAgDNAkvCw94AA6EwAaExAaEzww)Will
Oliver / POOL / PAP

Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego
2025 r.

# "Katastrofalna" wpadka CIA"""

        clean_text = "Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego 2025 r."

        expected_text = """Rzecznik
Patela nie odpowiedział na prośbę o komentarz.

![Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego 2025 r.](https://ocdn.eu/pulscms-transforms/1/i-bk9kpTURBXy8wOGY1YzY2YWY1NjAxYjA4ZjExNzc5NTBlYzQyYWU5ZC5qcGeSlQLNA6wAwsOVAgDNAkvCw94AA6EwAaExAaEzww)Will
Oliver / POOL / PAP

Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego 2025 r.

# "Katastrofalna" wpadka CIA"""

        # Wynik uzyskany z funkcji
        result = remove_new_line_only_in_string(markdown, clean_text)

        # Porównanie
        self.assertEqual(result, expected_text)


if __name__ == "__main__":
    unittest.main()
