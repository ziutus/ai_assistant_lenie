import unittest

from library.lenie_markdown import md_get_images_as_links

class MyTestCase(unittest.TestCase):
    def test_extract_links_as_images(self):
        markdown = "[![](https://ocdn.eu/pulscms-transforms/1/uLnk9kpTURBXy9iNDRlODE4OTU2ZGE1Y2I3NmYzZjEyMmY0MmYwZTZhYi5qcGeSlQLNAu4AwsOVAgDNAu7Cw94AA6EwAaExAaEzww)](https://www.onet.pl/informacje/onetwiadomosci/specjalne-wydanie-raportu-miedzynarodowego-jak-sie-zapisac/gc43ldn,79cfc278?5360)"

        md_text, extracted_links, extracted_images = md_get_images_as_links(markdown)
        self.assertEqual(True, True)  # add assertion here


if __name__ == '__main__':
    unittest.main()
