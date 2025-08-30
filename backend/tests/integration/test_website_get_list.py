import os
import unittest
from server import app

os.environ['DEBUG'] = 'false'


class TestWebsiteList(unittest.TestCase):
    def test_website_list(self):
        self.app = app.test_client()

        response = self.app.get('/website_list')

        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["message"], "Dane odczytane pomyślnie.")
        self.assertEqual(data["encoding"], "utf8")

        self.assertIsInstance(data["websites"], list)


if __name__ == '__main__':
    unittest.main()
