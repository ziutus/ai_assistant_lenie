import unittest

from library.lenie_markdown import md_square_brackets_in_one_line


class TestMdSquareBracketsInOneLine(unittest.TestCase):
    def test_basic_case(self):
        text = "[John \nRatcliffe](link) był \nuważany"
        expected = "[John Ratcliffe](link) był \nuważany"
        self.assertEqual(md_square_brackets_in_one_line(text), expected)

    def test_no_square_brackets(self):
        text = "This is some \ntext without brackets."
        expected = "This is some \ntext without brackets."
        self.assertEqual(md_square_brackets_in_one_line(text), expected)

    # def test_nested_square_brackets(self):
    #     text = "[Outer [Inner \ntext]\nstill outer]"
    #     expected = "[Outer [Inner text]still outer]"
    #     self.assertEqual(md_square_brackets_in_one_line(text), expected)

    def test_empty_string(self):
        text = ""
        expected = ""
        self.assertEqual(md_square_brackets_in_one_line(text), expected)

    def test_only_newlines_in_brackets(self):
        text = "[\n\n\n]"
        expected = "[]"
        self.assertEqual(md_square_brackets_in_one_line(text), expected)


    def test_real_1(self):
        text = """
przed tym [nad
tym ](https://onet), [Francji
Emmanuel] Macron
"""

        expected = """
przed tym [nad tym ](https://onet), [Francji Emmanuel] Macron
"""

        self.assertEqual(md_square_brackets_in_one_line(text), expected)

    def test_real_2(self):
        text = """
[![](https://test.pl)Ma
pra](https://test2.pl)
"""

        expected = """
[![](https://test.pl)Ma pra](https://test2.pl)
"""

        self.assertEqual(md_square_brackets_in_one_line(text), expected)


if __name__ == "__main__":
    unittest.main()
