import os.path
import re
import json
import logging
from dotenv import load_dotenv

from markitdown import MarkItDown
from html2markdown import convert
import html2text

from library.lenie_markdown import get_images_with_links_md, links_correct, process_markdown_and_extract_links, \
    md_square_brackets_in_one_line, md_split_for_emb
from library.stalker_web_document import StalkerDocumentStatusError
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.api.aws.s3_aws import s3_file_exist, s3_take_file

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

S3_BUCKET_NAME = os.getenv("AWS_S3_WEBSITE_CONTENT")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")


def calculate_reduction(html_size, markdown_size):
    return ((html_size - markdown_size) / html_size) * 100

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


def onet_see_also_process_markdown_and_extract_links_with_images(markdown_text):
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

def load_regex_from_file(file_path):
    """
    Funkcja wczytująca wyrażenie regularne z zewnętrznego pliku.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Plik z regułami nie został znaleziony: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        logger.debug(f"Lead_regx_from_file: reading file: {file_path} ")
        return f.read().strip()


def generate_links_regex(links):
    patterns = [re.escape(f'[{link["description"]}]({link["url"]})') for link in links]
    return '|'.join(patterns)


wb_db = WebsitesDBPostgreSQL()
# documents = wb_db.get_documents_by_url("https://www.money.pl/")
documents = [7789]
page_url = " https://www.onet.pl/informacje/businessinsider/"
online = True
embedding_update = False
ignore_regexp_issue = False
cache_dir = "tmp/markdown"
split_limit = 300

page_regexp_map = {
    "https://www.money.pl": [
        "data/pages_analyze/money.regex",
        "data/pages_analyze/money2.regex",
        "data/pages_analyze/money3.regex",
        "data/pages_analyze/money4.regex",
        "data/pages_analyze/money5.regex"
    ],
    "https://wiadomosci.wp.pl/": [
        "data/pages_analyze/wiadomosci_wp_pl_1.regex",
        "data/pages_analyze/wiadomosci_wp_pl_2.regex"
    ],
    "https://www.onet.pl/informacje/onetwiadomosci": [
        "data/pages_analyze/onet_pl_informacje_wiadomosci.regex",
        "data/pages_analyze/onet_pl_informacje_wiadomosci_2.regexp"
    ],
    "https://www.onet.pl/informacje/ppo": [
        "data/pages_analyze/onet_pl_informacje_ppo.regex",
    ],
    "https://www.onet.pl/turystyka/onetpodroze": [
        "data/pages_analyze/onet_pl_podroze.regex"
    ],
    "https://www.onet.pl/informacje/businessinsider": [
        "data/pages_analyze/onet_pl_informacje_businessInsider.regex"
    ],
    # "": []
}

page_rules_map = {
    "https://www.money.pl": ["data/pages_rules/money.rules"]
}

if __name__ == '__main__':


    if not os.path.exists(cache_dir):
        logger.debug(f"Creating cache directory {cache_dir}")
        os.makedirs(cache_dir)

    for document_id in documents:

        web_doc = StalkerWebDocumentDB(document_id=document_id)

        logger.info(f"Working on document_id {document_id}")
        metadata = {}
        cache_file_html = f"{cache_dir}/{document_id}.html"
        cache_file_step_1_md = f"{cache_dir}/{document_id}_step_1.md"
        cache_file_step_2_md = f"{cache_dir}/{document_id}_step_2.md"

        logger.info("Step 1: preparing markdown from HTML file")
        logger.debug("Taking markdown content from local cache or from remote cache (S3)")

        if not os.path.isfile(cache_file_step_1_md) and not os.path.isfile(cache_file_html):
            logger.debug("Taking raw html file from cache in Amazon S3")

            if not web_doc.s3_uuid:
                logger.debug("Doesn't exist s3_uuid, exiting...")
                continue

            if not s3_file_exist(S3_BUCKET_NAME, web_doc.s3_uuid + ".html"):
                logger.debug("I can't find file in S3 cache")
                continue

            logger.debug("the HTML file exist in S3 cache")
            if s3_take_file(S3_BUCKET_NAME, web_doc.s3_uuid + ".html", cache_file_html):
                logger.debug("The HTML file has been copy to local cache")
            else:
                logger.debug("Can't download file from S3 cache, exiting...")
                continue

        if os.path.isfile(cache_file_step_1_md):
            logger.debug("DEBUG: 1a. Taking raw markdown file from cache")
            with open(cache_file_step_1_md, "r", encoding="utf-8") as f:
                result = f.read()
        else:
            logger.debug("DEBUG: 1b. Taking raw html file from cache")
            mdit = MarkItDown()
            result = mdit.convert(cache_file_html).text_content

        md_size = len(result)
        html_size = os.path.getsize(cache_file_html)

        logger.debug(f"Rozmiar HTML: {html_size} bajtów")

        reduction_percentage = calculate_reduction(html_size, md_size)
        logger.debug(f"MarkItDown reduction: {reduction_percentage:.2f}%")
        markdown_text = result

        if reduction_percentage < 30:
            logger.debug("Looks like MarkItDown didn't converted to markdown, choosing next metod: html2text")
            with open(cache_file_html, "r", encoding="utf-8") as f:
                html = f.read()

                markdown = convert(html)
                md_size_2 = len(markdown)

                reduction_markdown_percentage = calculate_reduction(html_size, md_size_2)
                logger.debug(f"Markdown reduction: {reduction_markdown_percentage:.2f}%")
                markdown_text = markdown

                if reduction_markdown_percentage < 30:

                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = False
                    markdown_content = h.handle(html)

                    markdown_size = len(markdown_content)
                    reduction_html2text_percentage = calculate_reduction(html_size, markdown_size)

                    logger.debug(f"html2Text reduction: {reduction_html2text_percentage:.2f}%")

                    markdown_text = markdown_content

                    if reduction_html2text_percentage < 30:
                        logger.error("ERROR: Something wrong with transformation to markdown, taking next document...")
                        continue

        with open(cache_file_step_1_md, 'w', encoding="utf-8") as file:
            file.write(markdown_text)

        logger.info("Step 2: taking article content from markdown (ignoring portal links, disclaimers, user comments etc")
        logger.debug("Taking URL from database")
        page_url = web_doc.url
        logger.debug(f"URL: {page_url}\n")

        if web_doc.document_state_error == StalkerDocumentStatusError.REGEX_ERROR and not ignore_regexp_issue:
            logger.info("Ignoring document as is REGEX_ERROR, to work on it, change ignore_regexp_issue to 'True'")
            continue

        found_rules = False
        regexp_rules_file = None
        extracted_text: str = ""
        for page_rules in page_regexp_map:
            if page_url.find(page_rules) != -1:
                logger.debug("I found rules for this page, let's check if they are working")
                # pprint(page_regexp_map[page_rules])

                for rules_file in page_regexp_map[page_rules]:
                    logger.debug(f"Checking file: {rules_file}")
                    regexp_page = load_regex_from_file(rules_file)
                    # print(f"TRACE: regexp_page: {regexp_page}")
                    match = re.search(regexp_page, markdown_text, re.VERBOSE | re.DOTALL)

                    if match:
                        logger.debug(f"Regex defined in {rules_file} for finding article body is working.")
                        extracted_text = match.group('article_text').strip() if match else "Nie znaleziono treści"
                        found_rules = True
                        regexp_rules_file = rules_file
                        break
                    else:
                        logger.debug(f"Nie znaleziono dopasowania z regułami z pliku {rules_file}.")
                        continue

        if not found_rules:
            logger.error(f"Can't find rules to analyze page {page_url}, time to check next one...")
            continue

        logger.debug(f"DEBUG: will use regex rule file: {regexp_rules_file}")

        with open(cache_file_step_2_md, 'w', encoding="utf-8") as file:
            file.write(extracted_text)

        markdown = extracted_text

        logger.info("\nStep 3 - correcting links multiline issue")

        logger.debug(" Putting links into one line")
        markdown = links_correct(markdown)
        with open(f"{cache_dir}/{document_id}_step_3.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.debug(" Putting squre brackets into one line")
        markdown = md_square_brackets_in_one_line(markdown)
        with open(f"{cache_dir}/{document_id}_step_3_1.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.info("\nStep 4 - converting markdown to text and creating metadata part for links and images")
        logger.debug("4.1 Extracting images from markdown")
        markdown, metadata["images_step4"] = get_images_with_links_md(markdown)

        with open(f"{cache_dir}/{document_id}_step_4_1.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.debug("Removing NBSP from markdown")
        markdown = markdown.replace(' ', ' ')

        logger.debug("Removing img from markdown")
        images_regex = r"img:\d+"
        markdown = re.sub(images_regex, '', markdown)

        logger.debug("Removing info strings")
        markdown = markdown.replace("*Dalsza część artykułu pod materiałem wideo*", "")

        logger.debug("Formating text by removing multiple empty lines and spaces")
        # new_markdown = re.sub('\n+', '\n', new_markdown)
        markdown = re.sub(' +', ' ', markdown)
        markdown = re.sub(r'\n*##', '\n\n##', markdown)

        logger.debug("Removing links from markdown and adding into metadata part")
        markdown, metadata["links2"] = process_markdown_and_extract_links(markdown)

        with open(f"{cache_dir}/{document_id}_step_4_2_without_links.md", 'w', encoding="utf-8") as file:
            logger.debug("Writing markdown to file from step 4")
            file.write(markdown)

        logger.info("\nStep 5: cleaning text for each big portal from external links inside text (not needed for embedding)")

        logger.debug("Onet: Extracting links with images from markdown")
        output_json = onet_see_also_process_markdown_and_extract_links_with_images(markdown)
        metadata["links"] = output_json['links']
        markdown = output_json['markdown']

        if page_url.startswith("https://www.onet.pl/informacje/onetwiadomosci"):
            logger.debug("Using special rules for onet.pl informacje onetwiadomosci")
            markdown = re.sub(r"^\*\s\*\*.*?\*\*", "", markdown, flags=re.MULTILINE)

        with open(f"{cache_dir}/{document_id}_step_5.md", 'w', encoding="utf-8") as file:
            logger.debug("Writing markdown to file from step 5")
            file.write(markdown)

        logger.debug("Writing final metadata file")
        with open(f"{cache_dir}/{document_id}.json", 'w', encoding="utf-8") as file:
            file.write(json.dumps(metadata, indent=4))


        logger.debug("Step 6: cleaning markdown document")
        markdown = re.sub(r'\r\n', '\n', markdown)

        markdown = re.sub(r'^\s+$', '\n', markdown)
        # markdown_text = re.sub(r'\n+', '\n', markdown_text)
        markdown = re.sub(r'\*\*\n+\s*', '**\n', markdown)

        if page_url.startswith("https://www.onet.pl/informacje/businessinsider"):
            markdown = re.sub(r'^\*\*Zobacz także:\*\*.*$', '', markdown, flags=re.MULTILINE)
        if page_url.startswith("https://www.onet.pl/informacje/onetwiadomosci"):
            markdown = re.sub(r'^\s*Dalszy\sciąg\smateriału\spod\swideo\s*$', '', markdown, flags=re.MULTILINE)

        markdown = popraw_markdown(markdown)
        markdown = re.sub('\n{3,10}', '\n\n', markdown)

        with open(f"{cache_dir}/{document_id}_step_6.md", "w", encoding="utf-8") as f:
            f.write(markdown)

        logger.info(f"Raw text has {len(markdown.split())} words")
        parts = md_split_for_emb(markdown)
        logger.info(f"Text has been split into {len(parts)} parts")

        print("\n>FINAL DATA<\n")
        for i, part in enumerate(parts):
            print("----")
            print(f"part {i+1} has {len(part.split())} words")
            print(part)

        # if embedding_update:
        #     parts_txt = []
        #     for part in parts:
        #         parts_txt.append(markdown_to_text(part))
        #
        #     wb_db = WebsitesDBPostgreSQL()
        #     web_doc = StalkerWebDocumentDB(document_id=document_id)
        #     web_doc.embedding_add_by_parts(model=EMBEDDING_MODEL, parts=parts_txt)
        #     web_doc.text_md = markdown_text
        #     web_doc.text = markdown_to_text(markdown_text)
        #     web_doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST
        #     web_doc.save()

exit(0)
