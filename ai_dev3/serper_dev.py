import http.client
import json
from dotenv import load_dotenv
import os
from pprint import pprint
import hashlib

load_dotenv()

query="Tomasz Smolarek Chipy"
query_md5 = hashlib.md5(query.encode()).hexdigest()
cache_dir = "tmp/serper_dev"
cache_filename = f"{cache_dir}/{query_md5}.json"

os.makedirs(cache_dir, exist_ok=True)

if os.path.isfile(cache_filename):
  print("File already exists in cache")
  data = json.load(open(cache_filename))
  pprint(data)
  exit()


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
pprint(data.decode("utf-8"))
pprint(f"MD5 hash of the query: {query_md5}")

with open(cache_filename, "w", encoding="utf-8") as file:
  file.write(data.decode("utf-8"))
  print(f"File saved in cache {cache_filename}")

