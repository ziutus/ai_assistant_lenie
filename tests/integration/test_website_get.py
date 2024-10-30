import unittest
import os
from server import app

os.environ['DEBUG'] = 'false'


class TestWebsiteGetById(unittest.TestCase):

    def setUp(self):
        # Ustawienie klienta testowego Flask
        self.app = app.test_client()

    def test_website_get_by_id_success(self):
        # Testowanie poprawnego przypadku z id dostępnym w danych
        response = self.app.get('/website_get?id=1')
        self.assertEqual(response.status_code, 200)
        expected_response = {"website_id": 1, "name": "Example Website"}
        self.assertEqual(response.json, expected_response)

    def test_website_get_by_id_missing_id(self):
        # Testowanie przypadku brakującego id w danych
        response = self.app.get('/website_get')
        self.assertEqual(response.status_code, 400)
        expected_response = {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}
        self.assertEqual(response.json, expected_response)

    def test_website_get_by_id_invalid_id(self):
        # Testowanie przypadku nieprawidłowego id (np. nieistniejącego)
        response = self.app.get('/website_get?id=999')
        self.assertEqual(response.status_code, 404)
        expected_response = {"status": "error", "message": "Nie znaleziono strony o podanym id"}
        self.assertEqual(response.json, expected_response)


if __name__ == '__main__':
    unittest.main()
