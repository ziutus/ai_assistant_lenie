import unittest
import sys
import os
from pprint import pprint
import uuid

os.environ['DEBUG'] = 'false'
# os.environ['DEBUG'] = 'true'

sys.path.append("library")
from server import app


class TestWebsiteGetById(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()

    def test_website_add(self):

        example_data = {
            "title": "Example Website",
            "summary": "Example summary",
            "url": f"https://example.com/{str(uuid.uuid4())}",
            "language": "pl",
            "tags": "example, test",
            "text": "Example text",
            "paywall": False,
            "saveContentToDatabase": "true"
        }

        # Testowanie poprawnego przypadku z id dostępnym w danych
        response = self.app.post('/save_website', data=example_data)
        example_data["id"] = response.json["id"]
        self.assertEqual(response.status_code, 200)

        response = self.app.get(f"/website_get?id={example_data['id']}")
        response_json = response.json
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json["url"], example_data["url"])
        self.assertEqual(response_json["title"], example_data["title"])
        self.assertEqual(response_json["summary"], example_data["summary"])
        self.assertEqual(response_json["language"], example_data["language"])
        self.assertEqual(response_json["tags"], example_data["tags"])
        self.assertEqual(response_json["text"], example_data["text"])

        example_data["title"] = "Example Website 2"
        example_data["summary"] = "Updated Example Summary"
        example_data["language"] = "en"
        example_data["tags"] = "updated, test"
        example_data["text"] = "Updated Example Text"
        example_data["paywall"] = True

        self.app.post('/save_website', data=example_data)

        response = self.app.get(f"/website_get?id={example_data['id']}")
        response_json = response.json
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json["url"], example_data["url"])
        self.assertEqual(response_json["title"], example_data["title"])
        self.assertEqual(response_json["summary"], example_data["summary"])
        self.assertEqual(response_json["language"], example_data["language"])
        self.assertEqual(response_json["tags"], example_data["tags"])
        self.assertEqual(response_json["text"], example_data["text"])
        # self.assertEqual(response_json["paywall"], example_data["paywall"])

        response = self.app.get(f"/website_delete?id={example_data['id']}")
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
