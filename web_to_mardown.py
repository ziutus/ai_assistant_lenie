import json
import os
import re

import boto3
from dotenv import load_dotenv

from markitdown import MarkItDown

from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentType, \
    StalkerDocumentStatusError
# Importacja własnych modułów
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.text_functions import remove_before_regex, remove_last_occurrence_and_after
from library.website.website_download_context import download_raw_html, webpage_raw_parse

# Ładowanie zmiennych środowiskowych
load_dotenv()

def remove_matching_lines(input_text):
    # Wyrażenie regularne dopasowujące podany format
    pattern = r'^\*\s\[\*\*.*\*\*\]\(https?://[^\)]+\)$'
    # Filtruj linie, które nie pasują do wzorca
    cleaned_lines = [line for line in input_text.splitlines() if not re.match(pattern, line)]
    # Połącz linie z powrotem w tekst
    return '\n'.join(cleaned_lines)


s3_bucket = os.getenv("AWS_S3_WEBSITE_CONTENT")

# s3_uuid = "49352d21-e84d-408f-8c93-21e7e7e22d53"
# url="https://www.onet.pl/informacje/onetwiadomosci/idealny-partner-tajwan-buduje-armie-dronow-dla-zachodu-chce-pomoc-stanom-zjednoczonym/b2z12d9,79cfc278"

s3_uuid = "74eaaa8c-2d3d-4c70-941e-430e37bcebd2"
url="https://www.onet.pl/informacje/nowaeuropawschodnia/ujgurzy-w-syrii-geopolityczny-fatalizm-turkiestanu-wschodniego/5fnp1fc,30bc1058"

boto_session = boto3.session.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

s3 = boto_session.client('s3')

try:
    print(f"* Reading text of article from S3 bucket >{s3_bucket}< and file: >{s3_uuid}.html<", end=" ")
    obj = s3.get_object(Bucket=s3_bucket, Key=f"{s3_uuid}.html")
    content = obj['Body'].read().decode('utf-8')

    page_file = f"tmp/{s3_uuid}.html"
    with open(f"{page_file}", 'w', encoding="utf-8") as file:
        file.write(content)

    md = MarkItDown()
    result = md.convert(page_file)
    # web_doc = StalkerWebDocumentDB(url)
    # web_doc.text = content

    md_file = f"tmp/{s3_uuid}.md"
    with open(f"{md_file}", 'w', encoding="utf-8") as file:
        file.write(result.text_content)

    md_clean_file = f"tmp/{s3_uuid}_clean.md"
    md_cleaned = result.text_content

    md_cleaned = remove_before_regex(md_cleaned, r"min czytania")
    md_cleaned = remove_before_regex(md_cleaned, r"Lubię to")
    md_cleaned = remove_last_occurrence_and_after(md_cleaned, r"\*Dziękujemy, że przeczytałaś/eś nasz artykuł do końca.")

    md_cleaned = remove_matching_lines(md_cleaned)

    with open(f"{md_clean_file}", 'w', encoding="utf-8") as file:
        file.write(md_cleaned)


    print('[DONE]')
    #
    # web_doc.analyze()
    # web_doc.validate()
    #
    # print(
    #     "* ALL DONE, updating state to NEED_MANUAL_REVIEW (cleaning of text is needed) as it is >webpage<",
    #     end=" ")
    # web_doc.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
    # print("[DONE]")
    # web_doc.save()

except Exception as e:
    print(f'An error occurred: {e}')
    exit(1)

