import unittest
import re
from library.lenie_markdown import get_images_with_links_md


class TestGetImagesWithLinksMd(unittest.TestCase):

    def test_get_images_with_links_with_description_2(self):
        markdown_input = """Rzecznik
Patela nie odpowiedział na prośbę o komentarz.

![Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21
lutego 2025 r.](https://ocdn.eu/pulscms-transforms/1/i-bk9kpTURBXy8wOGY1YzY2YWY1NjAxYjA4ZjExNzc5NTBlYzQyYWU5ZC5qcGeSlQLNA6wAwsOVAgDNAkvCw94AA6EwAaExAaEzww)Will
Oliver / POOL / PAP

Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego
2025 r.

# "Katastrofalna" wpadka CIA"""

        image_expected =  {
            'alt_text': 'Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego 2025 r.',
            'description': 'Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego 2025 r.',
            'owner': 'Will Oliver / POOL / PAP',
            'url': 'https://ocdn.eu/pulscms-transforms/1/i-bk9kpTURBXy8wOGY1YzY2YWY1NjAxYjA4ZjExNzc5NTBlYzQyYWU5ZC5qcGeSlQLNA6wAwsOVAgDNAkvCw94AA6EwAaExAaEzww'
        }

        # Oczekiwany wynik (poprawiony URL sklejony w jeden ciąg)
        markdown_expected = """Rzecznik
Patela nie odpowiedział na prośbę o komentarz.

picture[0]:"Kash Patel podczas zaprzysiężenia na dyrektora FBI, Waszyngton, USA, 21 lutego 2025 r."

# "Katastrofalna" wpadka CIA"""

        # Wywołanie funkcji
        markdown, images = get_images_with_links_md(markdown_input)

        # Sprawdzenie, czy wynik jest zgodny z oczekiwaniami
        self.assertEqual(markdown, markdown_expected)
        self.assertEqual(images[0]["url"], image_expected["url"])
        self.assertEqual(images[0]["alt_text"], image_expected["alt_text"])
        self.assertEqual(images[0]["description"], image_expected["description"])


# Jeśli uruchamiamy test bezpośrednio
if __name__ == "__main__":
    unittest.main()
