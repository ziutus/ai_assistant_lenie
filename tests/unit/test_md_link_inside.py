import unittest

from library.lenie_markdown import links_correct


class MyTestCase(unittest.TestCase):
    def test_something(self):
        link_to_correct = """https://google.
com"""
        link_expected = "https://google.com"

        link_corrected = links_correct(link_to_correct)

        self.assertEqual(link_expected, link_corrected)


if __name__ == '__main__':
    unittest.main()
