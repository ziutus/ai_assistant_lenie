import unittest
from library.website.website_paid import website_is_paid


class TestWebsitePaid(unittest.TestCase):

    def test_paid_website(self):
        link = "https://wyborcza.pl/"
        self.assertTrue(website_is_paid(link))

    def test_paid_website_with_onet_domain_and_paid_path(self):
        link = "https://onet.pl/newsweek/abc.html"
        self.assertTrue(website_is_paid(link))

    # def test_paid_website_with_onet_domain_and_not_paid_path(self):
    #     link = "https://onet.pl/newsweb/abc.html"
    #     self.assertFalse(website_is_paid(link))

    def test_free_website(self):
        link = "https://testfree.com/"
        self.assertFalse(website_is_paid(link))


if __name__ == '__main__':
    unittest.main()
