import unittest
import sys
import os

os.environ['DEBUG'] = 'false'

sys.path.append("library")
from server import app


class FlaskTestCase(unittest.TestCase):

    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_hello_world(self):
        data = { "url": "https://www.google.com/" }
        response = self.client.post('/website_is_paid', data=data)
        self.assertEqual(response.status_code, 200)
        response_data = response.get_json()
        self.assertEqual(response_data["is_paid"], False)


if __name__ == '__main__':
    unittest.main()
