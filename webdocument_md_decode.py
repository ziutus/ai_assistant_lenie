import os.path
import re
import json
from markitdown import MarkItDown
from dotenv import load_dotenv
from pprint import pprint

from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.api.aws.s3_aws import s3_file_exist,s3_take_file

load_dotenv()

S3_BUCKET_NAME = os.getenv("AWS_S3_WEBSITE_CONTENT")

def popraw_markdown(tekst):
    linie = tekst.splitlines()
    wynik = []
    for linia in linie:
        if linia.startswith("**") and linia.endswith("**"):
            if wynik and wynik[-1] != '\n':
                wynik.append("")
            wynik.append(linia)
        elif linia.startswith("## "):
            if wynik and wynik[-1] != '\n':
                wynik.append("")
            wynik.append(linia)
        else:
            wynik.append(linia)
    return "\n".join(wynik)

def split_for_emb(part, split_limit=300, level=0):
    parts = []
    if level == 0:
        delimiter = "\n# "
        splitter = "---split---\n# "
    elif level == 1:
        delimiter = "\n## "
        splitter = "---split---\n## "
    elif level == 2:
        delimiter = "\n### "
        splitter = "---split---\n### "
    elif level == 3:
        delimiter = "\n**"
        splitter = "---split---\n**"

    else:
        return [part]

    word_count = len(part.split())
    if word_count < split_limit:
        return [part]

    parts_tmp = part.replace(delimiter, splitter)
    parts_tmp = parts_tmp.split("---split---")
    for part in parts_tmp:
        result = split_for_emb(part, split_limit, level+1)
        parts.extend(result)
    return parts

def process_markdown_and_extract_links_with_images(markdown_text):
    # Regex dla wyszukiwania linków z obrazkami w Markdown
    image_links_regex = r'\[\!\[\]\((.*?)\)\]\((.*?)\)'
    description_regex = r'Zobacz także:\[(.*?)\]'

    # Wyszukiwanie dopasowań dla linków z obrazkami
    matches = re.findall(image_links_regex, markdown_text)

    # Wyszukiwanie opisów (opcjonalnych)
    descriptions = re.findall(description_regex, markdown_text)

    # Budowanie listy wyników i modyfikacja tekstu Markdown
    result = []

    updated_text = markdown_text
    for i, match in enumerate(matches):
        image_url, link_url = match
        description = descriptions[i] if i < len(descriptions) else ""

        # Dodanie obiektu do wynikowej listy
        result.append({
            "image": image_url,
            "link": link_url,
            "description": description
        })

        # Zamiana wystąpienia linku na `[i]`
        updated_text = updated_text.replace(f'[![]({image_url})]', f'see_also:{i}', 1)
        updated_text = updated_text.replace(f'({link_url})Zobacz także:[{description}]({link_url})', '', 1)
        updated_text = updated_text.replace(f'see_also:{i}', '', 1)

    # Zwrócenie zaktualizowanego tekstu Markdown i danych JSON
    return {
        "markdown": updated_text,
        "links": result
    }

def replace_images_in_markdown(markdown_text):
    images_regex = r'(\!\[(.*?)\]\((.*?)\))'

    matches = re.findall(images_regex, markdown_text)

    images = [{"alt_text": alt_text, "image_url": url} for _, alt_text, url in matches]

    for i, match in enumerate(matches):
        full_match, _, _ = match
        markdown_text = markdown_text.replace(full_match, f' img:{i} ', 1)

    return markdown_text, images


def load_regex_from_file(file_path):
    """
    Funkcja wczytująca wyrażenie regularne z zewnętrznego pliku.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Plik z regułami nie został znaleziony: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def generate_links_regex(links):
    patterns = [re.escape(f'[{link["description"]}]({link["url"]})') for link in links]
    return '|'.join(patterns)


def process_markdown_and_extract_links(md_text):
    # Wyrażenie regularne do wyszukiwania linków
    pattern = re.compile(r'\[(.*?)\]\((.*?)\)')

    links = pattern.findall(md_text)
    output = [{"text": text, "link": url} for text, url in links]

    # Zastąpienie linków tekstami link:ID
    for i in range(len(links)):
        md_text = md_text.replace(f'[{links[i][0]}]({links[i][1]})', f'{output[i]["text"]}')

    return md_text, output

# documents = wb_db.get_documents_by_url("https://www.money.pl/")
documents=[7534]
page_url = " https://www.onet.pl/informacje/businessinsider/"

page_regexp_map = {
    "https://www.money.pl": [
        "data/pages_analyze/money.regex",
        "data/pages_analyze/money2.regex",
        "data/pages_analyze/money3.regex"
    ],
    "https://wiadomosci.wp.pl/": [
        "data/pages_analyze/wiadomosci_wp_pl_1.regex"
    ],
    "https://www.onet.pl/informacje/onetwiadomosci": ["data/pages_analyze/onet_pl_informacje_wiadomosci.regex"],
    "https://www.onet.pl/turystyka/onetpodroze": ["data/pages_analyze/onet_pl_podroze.regex"],
    "https://www.onet.pl/informacje/businessinsider": ["data/pages_analyze/onet_pl_informacje_businessInsider.regex"]
    # "": []
}

page_rules_map = {
    "https://www.money.pl": ["data/pages_rules/money.rules"]
}

if __name__ == '__main__':

    for document_id in documents:
        print(f"DEBUG: Working on document_id {document_id}")
        metadata = {}
        cache_file_md = f"tmp/markdown/{document_id}.md"
        cache_file_html = f"tmp/markdown/{document_id}.html"
        cache_file_output = f"tmp/markdown_output/{document_id}.md"
        cache_file_output_2 = f"tmp/markdown_output/{document_id}_2.md"


        print("Taking markdown content from local cache or from remote cache (S3)")
        if os.path.isfile(cache_file_md):
            print("DEBUG: 1. Taking raw markdown file from cache")
            with open(cache_file_md, "r", encoding="utf-8") as f:
                result = f.read()
        else:
            print("DEBUG: 1a. Taking raw markdown from Amazon S3")
            wb_db = WebsitesDBPostgreSQL()
            web_doc = StalkerWebDocumentDB(document_id=document_id)
            if web_doc.s3_uuid:
                if s3_file_exist(S3_BUCKET_NAME, web_doc.s3_uuid + ".html"):
                    print("I can download file from S3 cache")
                    if s3_take_file(S3_BUCKET_NAME, web_doc.s3_uuid + ".html", cache_file_html):
                        md = MarkItDown()
                        result = md.convert(cache_file_html)
                        with open(cache_file_md, 'w', encoding="utf-8") as file:
                            file.write(result.text_content)
                        result = result.text_content
                    else:
                        print("Can't download file from S3 cache, exiting...")
                        exit(3)
                else:
                    print("I can't download file from S3 cache")
                    exit(1)
            else:
                print("Doesn't exist s3_uuid, exiting...")
                exit(2)

        print("par 2: taking important content from markdown (ignoring portal links, disclaimers etc")
        found_rules = False
        regexp_rules_file = None
        extracted_text: str = ""
        for page_rules in page_regexp_map:
            if page_url.find(page_rules) != -1:
                print("DEBUG: I found rules for this page, let's check if they are working")
                # pprint(page_regexp_map[page_rules])

                for rules_file in page_regexp_map[page_rules]:
                    regexp_page = load_regex_from_file(rules_file)
                    match = re.search(regexp_page, result, re.VERBOSE | re.DOTALL)

                    if match:
                        extracted_text = match.group('article_text').strip() if match else "Nie znaleziono treści"
                        print(f"DEBUG: Regex defined in {rules_file} for finding article body is working.")
                        found_rules = True
                        regexp_rules_file = rules_file
                        break
                    else:
                        print(f"Nie znaleziono dopasowania z regułami z pliku {rules_file}.")
                        continue

        if not found_rules:
            print(f"ERROR: Can't find rules to analyze page {page_url}, time to check next one...")
            continue

        print(f"DEBUG: will use regex rule file: {regexp_rules_file}")

        with open(cache_file_output, 'w', encoding="utf-8") as file:
            file.write(extracted_text)

        print("Part 3 - converting markdown to text and creating metadata part for links and images")
        print("DEBUG: extracting links with images from markdown")
        output_json = process_markdown_and_extract_links_with_images(extracted_text)
        metadata["links"] = output_json['links']
        markdown = output_json['markdown']

        # with open(cache_file_output_2, 'w', encoding="utf-8") as file:
        #     file.write(markdown)
        # with open(f"tmp/markdown_output/{document_id}_2.json", 'w', encoding="utf-8") as file:
        #     file.write(json.dumps(metadata, indent=4))

        print("DEBUG: extracting images from markdown")
        new_markdown, metadata["images"] = replace_images_in_markdown(markdown)

        # with open(f"tmp/markdown_output/{document_id}_3.json", 'w', encoding="utf-8") as file:
        #     file.write(json.dumps(metadata, indent=4))
        #
        # with open(f"tmp/markdown_output/{document_id}_3.md", 'w', encoding="utf-8") as file:
        #     file.write(new_markdown)

        print("DEBUG: removing NBSP from markdown")
        new_markdown = new_markdown.replace(' ', ' ')
        # with open(f"tmp/markdown_output/{document_id}_4.md", 'w', encoding="utf-8") as file:
        #     file.write(new_markdown)

        print("DEBUG: Removing img from markdown")
        images_regex = r"img:\d+"
        new_markdown = re.sub(images_regex, '', new_markdown)
        # with open(f"tmp/markdown_output/{document_id}_5.md", 'w', encoding="utf-8") as file:
        #     file.write(new_markdown)

        print("DEBUG: removing info strings")
        # *Dalsza część artykułu pod materiałem wideo*
        new_markdown = new_markdown.replace("*Dalsza część artykułu pod materiałem wideo*", "")

        print("DEBUG: formating text by removing multiple empty lines and spaces")
        new_markdown = re.sub('\n+', '\n', new_markdown)
        new_markdown = re.sub(' +', ' ', new_markdown)
        new_markdown = re.sub(r'\n*##', '\n\n##', new_markdown)

        print("DEBUG: removing links from markdown and adding into metadata part")
        new_markdown, metadata["links2"] = process_markdown_and_extract_links(new_markdown)

        print("Part 3: cleaning text for each big portal from external links inside text (not needed for embedding)")
        if page_url.startswith("https://www.onet.pl/informacje/onetwiadomosci"):
            print("Using special rules for onet.pl informacje onetwiadomosci")
            new_markdown = re.sub(r"^\*\s\*\*.*?\*\*", "", new_markdown, flags=re.MULTILINE)


        print("Final part: writing markdown and metadata files")
        print("DEBUG: writing final metadata file")
        with open(f"tmp/markdown_output/{document_id}.json", 'w', encoding="utf-8") as file:
            file.write(json.dumps(metadata, indent=4))

        print("DEBUG: writing final markdown file")
        with open(f"tmp/markdown_output/{document_id}.md", 'w', encoding="utf-8") as file:
            file.write(new_markdown)

        print("Extra part: cleaning markdown document")
        markdown_text = re.sub('\r\n', '\n', new_markdown)

        markdown_text = re.sub(r'^\s+$', '\n', markdown_text)
        markdown_text = re.sub('\n+', '\n', markdown_text)
        markdown_text = re.sub('\*\*\n+\s*', '**\n', markdown_text)
        markdown_text = popraw_markdown(markdown_text)
        markdown_text = re.sub('\n{3,10}', '\n\n', markdown_text)

        with open(f"tmp/markdown_output/{document_id}_manual_test.md", "w", encoding="utf-8") as f:
            f.write(markdown_text)

        split_limit = 300
        print("Raw text has ", len(markdown_text.split()), " words")

        parts = split_for_emb(markdown_text)

        print("\n>FINAL DATA<\n")
        for part in parts:
            print("----")
            print("part has words", len(part.split()))
            print(part)



exit(0)