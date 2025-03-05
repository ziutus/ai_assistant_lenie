import unittest

from library.lenie_markdown import process_markdown_and_extract_links


class MyTestCase(unittest.TestCase):
    def test_extract_links(self):
        markdown = """Z dyrektorką Wywiadu Narodowego Tulsi Gabbard.

[John Ratcliffe służył jako szef wywiadu podczas pierwszej administracji Trumpa](https://wiadomosci.onet.pl/swiat/jest-nowy-szef-cia-senat-usa-dal-zielone-swiatlo/tfpy43v) i był uważany za jednego z mniej kontrowersyjnych
pracowników gabinetu prezydenta, pomimo wcześniejszych obaw, że upolitycznił wywiad."""

        md_text, extracted_links = process_markdown_and_extract_links(markdown)
        self.assertEqual(True, False)  # add assertion here


if __name__ == '__main__':
    unittest.main()
