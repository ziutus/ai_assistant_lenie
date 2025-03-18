# import unittest
# import os
# from server import app
#
# os.environ['DEBUG'] = 'false'
#
#
# class TestWebsiteExist(unittest.TestCase):
#
#     def setUp(self):
#         self.app = app.test_client()
#         self.link_exist = 'https://wydarzenia.interia.pl/raport-media-zagraniczne/news-the-economist-austria-w-objeciach-rosyjskiego-niedzwiedzia,nId,6783510'
#         self.endpoint = '/website_exist'
#
#     def test_website_exist_with_json(self):
#         data = {'url': self.link_exist}
#         response = self.app.post(self.endpoint, json=data)
#         json_response = response.get_json()
#
#         self.assertEqual(response.status_code, 200)
#         self.assertEqual(json_response['status'], 'success')
#         self.assertEqual(json_response['exist'], True)
#         self.assertEqual(json_response['url'], self.link_exist)
#
#     def test_website_exist_with_form_data(self):
#         data = {'link': self.link_exist}
#         response = self.app.post(self.endpoint, data=data)
#         json_response = response.get_json()
#
#         self.assertEqual(response.status_code, 200)
#         self.assertEqual(json_response['status'], 'success')
#         self.assertEqual(json_response['exist'], True)
#         self.assertEqual(json_response['url'], self.link_exist)
#
#     def test_website_exist_missing_data(self):
#         data = {}  # Missing 'link' key
#         response = self.app.post(self.endpoint, json=data)
#         json_response = response.get_json()
#
#         self.assertEqual(response.status_code, 400)
#         self.assertEqual(json_response['status'], 'error')
#         self.assertEqual(json_response['message'], "Brakujące dane. Upewnij się, że dostarczasz 'url'")
#
#
# if __name__ == '__main__':
#     unittest.main()
