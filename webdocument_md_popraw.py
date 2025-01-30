import os.path

from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.document_markdown import DocumentMarkDown
from dotenv import load_dotenv

from library.website.website_download_context import webpage_text_clean

from library.modules.ziutus.money_pl.plugin import page_money_pl

import re

load_dotenv()

wb_db = WebsitesDBPostgreSQL()

# documents = wb_db.get_documents_by_url("https://www.money.pl/")

documents=[87]


ignored_images = [
    'https://v.wpimg.pl/bGRlci5wTSYzDhVaGgxAM3BWQQpFHz0qPQIGEAdVTmUnTllLGhMLNCZDEB1UAwskfQENEBgHDiYxCQsGWRMHNXwcDQ4XCg',
    'https://v.wpimg.pl/MTkwNi5wYjUKFThaGgxvIElNbApFHxI1DwQtSxlVOHZRVWFfAkZ6Y11Of1AGRnlmX0d_RgJGfWFZQnZdBk95ZVpOfl8bByMzSQo',
    'https://v.wpimg.pl/eDYwMC5qSiU4FTtwGgpHMHtNbyBFGTopOBouYRlTEGZjVWJyAERWdGpYfHQGR1xwaEJ9dwFGVmsaMHtvAgEXKzoofXIHQVdxBkR9c01HVXR3HT0kFww',
    'https://v.wpimg.pl/ODY1Ny5wYCU4UzhKGgxtMHsLbBpFHxAlPUItWxlVOmZjE2FPDUF4cW0BfUwBQH53awB5VgJGf31gAnZOA0Z9d2EHe04bByEje0w',
    'https://v.wpimg.pl/MTkwNi5wYjUKFThaGgxvIElNbApFHxI1DwQtSxlVOHZRVWFfAkZ6Y11Of1AGRnlmX0d_RgJGfWFZQnZdBk95ZVpOfl8bByMzSQo',
    'https://v.wpimg.pl/NTkzOC5wYTUKGDlwGgxsIElAbSBFHxE1DwksYRlVO3ZRWGB1DUF5YV9KfHYBQH9nWUt4bAJHd2VTT3pzA0V5Y15DfHsbByAzSQc'
    # Dodaj tutaj więcej URL-ów do pominięcia
]








def generate_links_regex(links):
    patterns = [re.escape(f'[{link["description"]}]({link["url"]})') for link in links]
    return '|'.join(patterns)



if __name__ == '__main__':

    for document_id in documents:
        # make_again = True
        # while make_again:
            cache_file = f"tmp/markdown/{document_id}.md"
            cache_file_output = f"tmp/markdown_output/{document_id}.md"

            if os.path.isfile(cache_file):
                print("1. Taking raw markdown file from cache")
                with open(cache_file, "r", encoding="utf-8") as f:
                    result = f.read()

                result = webpage_text_clean("https://www.money.pl/test", result)

            else:
                print("1a. Taking raw markdown from database")
                web_doc = StalkerWebDocumentDB(document_id=document_id)

                result = webpage_text_clean(web_doc.url, web_doc.text_md)

                print("1b. Putting raw markdown to local cache file")
                with open(cache_file, "w", encoding="utf-8") as file:
                    file.write(result)

                print(web_doc.url)

            document_md = DocumentMarkDown()
            document_md.id = document_id
            document_md.text_md = result

            print("2. Extracting images and put into metadata part")
            document_md.extract_images_with_references(ignored_images)

            print("3. Extracting references and put into metadata part")
            document_md.extract_references_with_numbered_links()

            print("4. Use page function to analyze page text")
            result = page_money_pl(document_md.text_md)
        
            document_md.text_md = result["text_md"]
            document_md.created_at = result["created_at"]
            document_md.updated_at = result["updated_at"]
            document_md.author = result["author"]

            # link na końcu to nazwa działu
            print("9. Money.pl part - removing link part")
            word_to_remove = "gospodarka"
            result = re.sub(rf'(?i)\b{word_to_remove}\b\s+### Lista zdjęć', '', document_md.text_md).strip()

            with open(cache_file_output, "w", encoding="utf-8") as f:
                f.write(result)

            # user_input = input("Do you want to save the response to the database? [Y]es, Correct [A]gain,  [N]o, next: ").strip().lower()
            # if user_input in ["A", "a"]:
            #     make_again = True
            #     print("Poprawiamy jeszcze raz")
            #     continue
            #
            # if user_input in ["N", "n"]:
            #     make_again = False
            #     print("Ignoruje propozycje zmian, następny tekst...")
            #     break
            #
            # if user_input in ["yes", "y", "Y"]:
            #     web_doc.text = after
            #     web_doc.save()
            #     print("Poprawiony tekst zapisany w bazie danych.")
            #     break


exit(0)