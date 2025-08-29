import http.client
import json
from dotenv import load_dotenv
import os
from pprint import pprint
import hashlib

load_dotenv()

query="+48 791 033 055"

query = query.replace("+48", "").replace(" ", "").strip()
print(f"Will search {query}")

query_md5 = hashlib.md5(query.encode()).hexdigest()
cache_dir = "tmp/serper_dev"
cache_filename = f"{cache_dir}/{query_md5}.json"

os.makedirs(cache_dir, exist_ok=True)

if os.path.isfile(cache_filename):
  print("File already exists in cache")
  with open(cache_filename, "r", encoding="utf-8") as file:
    data = json.loads(file.read())
else:
  conn = http.client.HTTPSConnection("google.serper.dev")
  payload = json.dumps({
    "q": query
  })
  headers = {
    'X-API-KEY': os.environ.get('SERPER_DEV_APIKEY'),
    'Content-Type': 'application/json'
  }

  conn.request("POST", "/search", payload, headers)
  res = conn.getresponse()
  data = res.read()
  pprint(f"MD5 hash of the query: {query_md5}")

  with open(cache_filename, "w", encoding="utf-8") as file:
    file.write(data.decode("utf-8"))
    print(f"File saved in cache {cache_filename}")
    data = json.loads(data)

print("Analizyng data from google")
for item in data["organic"]:
  print ("---")
  print(item["position"])
  print(item["title"])
  print(item["snippet"])
  print(item["link"])
  # pprint(item)
