import unittest

from library.lenie_markdown import process_markdown_and_extract_links


class MyTestCase(unittest.TestCase):
    def test_extract_links(self):
        markdown = """Z dyrektorką Wywiadu Narodowego Tulsi Gabbard.

[John Ratcliffe służył jako szef wywiadu podczas pierwszej administracji Trumpa](https://wiadomosci.onet.pl/swiat/jest-nowy-szef-cia-senat-usa-dal-zielone-swiatlo/tfpy43v) i był uważany za jednego z mniej kontrowersyjnych
pracowników gabinetu prezydenta, pomimo wcześniejszych obaw, że upolitycznił wywiad."""

        md_text, extracted_links = process_markdown_and_extract_links(markdown)
        self.assertEqual(True, True)  # add assertion here


    def test_extract_links_as_images(self):
        markdown = "[![](https://ocdn.eu/pulscms-transforms/1/uLnk9kpTURBXy9iNDRlODE4OTU2ZGE1Y2I3NmYzZjEyMmY0MmYwZTZhYi5qcGeSlQLNAu4AwsOVAgDNAu7Cw94AA6EwAaExAaEzww)](https://www.onet.pl/informacje/onetwiadomosci/specjalne-wydanie-raportu-miedzynarodowego-jak-sie-zapisac/gc43ldn,79cfc278?5360)"

        md_text, extracted_links = process_markdown_and_extract_links(markdown)
        self.assertEqual(True, True)  # add assertion here


if __name__ == '__main__':
    unittest.main()
