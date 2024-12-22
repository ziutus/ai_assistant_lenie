import os
from pprint import pprint

import requests
from dotenv import load_dotenv

from library.embedding import get_embedding
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

# Ładowanie zmiennych środowiskowych
load_dotenv()

# directory = "tmp/tydzien3_2"
#
# reports = os.listdir(directory)
# reports_text = {}
#
# for report in reports:
#     with open(f"{directory}/{report}", "r", encoding="utf-8") as file:
#         reports_text[report] = file.read()
#
#
# pprint(reports_text)
#
# embd_model="amazon.titan-embed-text-v1"
#
# for report_file in reports_text:
#     web_document = StalkerWebDocumentDB(url=f"aidevs.pl/dummy.html?id={report_file}")
#     web_document.project = "aidevs3_tydzien3_2"
#     web_document.document_type = "text"
#     web_document.title = report_file
#     web_document.text = reports_text[report_file]
#     web_document.text_raw = reports_text[report_file]
#     web_document.set_document_type("text")
#     web_document.set_document_state("READY_FOR_EMBEDDING")
#     web_document.save()

numbers = list(range(7382, 7405))
model = "amazon.titan-embed-text-v2:0"
print(numbers)

# website_nb = 1
# embedding_needed_len = len(numbers)
# print(f"entries to analyze: {embedding_needed_len}")
# for website_id in numbers:
#     web_doc = StalkerWebDocumentDB(document_id=website_id)
#
#     progress = round((website_nb / embedding_needed_len) * 100)
#     print(f"Working on ID:{web_doc.id} ({website_nb} from {embedding_needed_len} {progress}%)"
#           f" {web_doc.document_type}" f"url: {web_doc.url}")
#     website_nb += 1
#
#     web_doc.embedding_add(model=model)
#     web_doc.save()

question = "W raporcie, z którego dnia znajduje się wzmianka o kradzieży prototypu broni"

embedds = get_embedding(model=model, text=question)

if embedds.status != "success" or len(embedds.embedding) == 0:
    print("Error during getting embedding for text")

websites = WebsitesDBPostgreSQL()

websites_list = websites.get_similar(embedds.embedding, model, limit=1, project="aidevs3_tydzien3_2")

date = websites_list[0]["title"].replace(".txt", "").replace("_", "-")

print("Answer is: ", date, "")


# json_data = {
#     "task": "wektory",
#     "apikey": os.environ.get('AI_DEV3_API_KEY'),
#     "answer": date
# }
#
# print(json_data)

# pprint(json_data["answer"]["2024-11-12_report-08-sektor_A1.txt"])

# response = requests.post("https://centrala.ag3nts.org/report", json=json_data)
# result = response.json()
# pprint(result)

exit(0)