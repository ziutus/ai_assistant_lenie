import os.path
import re
import json
import logging
from dotenv import load_dotenv
from pprint import pprint

from markitdown import MarkItDown
from html2markdown import convert
import html2text

from library.api.cloudferro.sherlock.sherlock_embedding import sherlock_create_embeddings
from library.lenie_markdown import get_images_with_links_md, links_correct, process_markdown_and_extract_links, \
    md_square_brackets_in_one_line, md_split_for_emb, md_get_images_as_links, md_remove_markdown
from library.stalker_web_document import StalkerDocumentStatusError, StalkerDocumentStatus
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

# interactive = True
documents = wb_db.get_documents_by_url("https://geekweek.interia.pl/")
# TODO: 7683 - need to correct related liks (//gospodarka/place-w-polsce-sa-duzo-nizsze-niz-na-zachodzie-a-ceny-takie-same-to-bzdura-analiza-7126921300134720a.html)
# TODO: 7741 - udostępnij artykuł - linki do ustąpienia do regexp: businessinsider_com_pl_2025_1.regex
# TODO: 7732 - lepszy podział na części do embeddingu
# TODO: 7687 - poprawić regexp geekweek_interia_pl_7687.regex
# documents = [ 7687 ]
# documents = wb_db.get_list(document_type="webpage", document_state="DOCUMENT_INTO_DATABASE")
# documents = wb_db.get_list(document_type="webpage", limit=700)
interactive = False
find_problems = False

text_to_md_check_only = False
online = True
embedding_update = False
ignore_regexp_issue = True
# cache_dir_base = "tmp/markdown"
cache_dir_base = r"C:\Users\ziutus\tmp\markdown"
split_limit = 200


page_regexp_map = {
    "https://www.money.pl": [
        "data/pages_analyze/money.regex",
        "data/pages_analyze/money2.regex",
        "data/pages_analyze/money3.regex",
        "data/pages_analyze/money4.regex",
        "data/pages_analyze/money5.regex",
        "data/pages_analyze/money_2025_1.regex",
        "data/pages_analyze/money_2025_6710.regex",
        "data/pages_analyze/money_2025_7728.regex",
        "data/pages_analyze/money_2025_7683.regex",
    ],
    "https://wiadomosci.wp.pl/": [
        "data/pages_analyze/wiadomosci_wp_pl_1.regex",
        "data/pages_analyze/wiadomosci_wp_pl_2.regex",
        "data/pages_analyze/wiadomosci_wp_pl_2025_1.regex",
        "data/pages_analyze/wiadomosci_wp_pl_2025_2.regex"
    ],
    "https://tech.wp.pl/": [
        "data/pages_analyze/wiadomosci_wp_pl_1.regex",
        "data/pages_analyze/wiadomosci_wp_pl_2.regex",
        "data/pages_analyze/wiadomosci_wp_pl_2025_1.regex",
        "data/pages_analyze/wiadomosci_wp_pl_2025_2.regex",
        "data/pages_analyze/tech_wp_pl_2025_1.regex"
    ],
    "https://www.onet.pl/informacje/onetwiadomosci": [
        "data/pages_analyze/onet_pl_informacje_wiadomosci.regex",
        "data/pages_analyze/onet_pl_informacje_wiadomosci_2.regexp"
    ],
    "https://www.onet.pl/turystyka/onetpodroze": [
        "data/pages_analyze/onet_pl_podroze.regex"
    ],
    "https://www.onet.pl/informacje/businessinsider": [
        "data/pages_analyze/onet_pl_informacje_businessInsider.regex"
    ],

    "https://wiadomosci.onet.pl/": [
        "data/pages_analyze/wiadomosci_onet_pl_7776.regex",
        "data/pages_analyze/wiadomosci_onet_pl_7635.regex",
        "data/pages_analyze/wiadomosci_onet_pl_7516.regex",
        "data/pages_analyze/wiadomosci_onet_pl_7147.regex",
        "data/pages_analyze/wiadomosci_onet_pl_7305.regex",
    ],

    "https://www.onet.pl/informacje/": [
        "data/pages_analyze/onet_pl_informacje_all.regex",
        "data/pages_analyze/onet_pl_informacje_all_2.regex",
        "data/pages_analyze/onet_pl_informacje_7411.regex",
    ],
    "https://www.onet.pl/": [
        "data/pages_analyze/onet_pl_informacje_7756.regex",
        "data/pages_analyze/onet_pl_informacje_7752.regex",
        "data/pages_analyze/onet_pl_informacje_7746.regex",
        "data/pages_analyze/onet_pl_informacje_7320.regex",
        "data/pages_analyze/onet_pl_informacje_ppo.regex",
        "data/pages_analyze/onet_pl_premium.regex",
    ],
    "https://www.onet.pl/motoryzacja/": [
        "data/pages_analyze/onet_pl_motoryzacja.regex"
    ],
    "https://businessinsider.com.pl/": [
        "data/pages_analyze/businessinsider_com_pl_2025_1.regex",
        "data/pages_analyze/businessinsider_com_pl_2025_2.regex"
    ],
    "https://wydarzenia.interia.pl/": [
        "data/pages_analyze/interia_pl_7732.regex",
        "data/pages_analyze/interia_pl_7553.regex",
        "data/pages_analyze/interia_pl_7510.regex",
        "data/pages_analyze/interia_pl_7504.regex",
        "data/pages_analyze/interia_pl_7496.regex",
    ],
    "https://geekweek.interia.pl": [
        "data/pages_analyze/geekweek_interia_pl_6837.regex",
        "data/pages_analyze/geekweek_interia_pl_7785.regex",
        "data/pages_analyze/geekweek_interia_pl_7687.regex",
    ],
    # "": []
}

page_rules_map = {
    "https://www.money.pl": ["data/pages_rules/money.rules"]
}

if __name__ == '__main__':


    if not os.path.exists(cache_dir_base):
        logger.debug(f"Creating cache directory {cache_dir_base}")
        os.makedirs(cache_dir_base)

    print(f"Documents to analyze: {len(documents)}")

    for document_tmp in documents:
        if type(document_tmp) is dict:
            document_id = document_tmp["id"]
        else:
            document_id = document_tmp

        logger.info(f"Working on document_id {document_id}")
        web_doc = StalkerWebDocumentDB(document_id=document_id)

        if web_doc.document_state == StalkerDocumentStatus.ERROR and web_doc.document_state_error == StalkerDocumentStatusError.ERROR_DOWNLOAD:
            logger.info("Ignoring document as is error is ERROR_DOWNLOAD...")
            continue

        # if web_doc.document_state == StalkerDocumentStatus.MD_SIMPLIFIED:
        #     logger.info("Ignoring document as is MD_SIMPLIFIED")
        #     continue


        cache_dir = f"{cache_dir_base}/{document_id}"
        if not os.path.exists(cache_dir):
            logger.debug(f"Creating cache directory {cache_dir}")
            os.makedirs(cache_dir)



        if web_doc.document_state_error == StalkerDocumentStatusError.REGEX_ERROR and not ignore_regexp_issue:
            logger.info("Ignoring document as is REGEX_ERROR, to work on it, change ignore_regexp_issue to 'True'")
            continue

        metadata = {"document_id": document_id}
        cache_file_html = f"{cache_dir}/{document_id}.html"
        cache_file_step_1_md = f"{cache_dir}/{document_id}_step_1_all.md"
        cache_file_step_2_md = f"{cache_dir}/{document_id}_step_2_1_article.md"

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

                reduction_percentage = calculate_reduction(html_size, md_size_2)
                logger.debug(f"Markdown reduction: {reduction_percentage:.2f}%")
                markdown_text = markdown

                if reduction_percentage < 30:

                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = False
                    markdown_content = h.handle(html)

                    markdown_size = len(markdown_content)
                    reduction_html2text_percentage = calculate_reduction(html_size, markdown_size)

                    logger.debug(f"html2Text reduction: {reduction_html2text_percentage:.2f}%")

                    markdown_text = markdown_content

        with open(cache_file_step_1_md, 'w', encoding="utf-8") as file:
            file.write(markdown_text)
            logger.info("Transformation from text to markdown completed")

        if reduction_percentage < 30 or reduction_percentage >= 98:
            logger.error("ERROR: Something wrong with transformation to markdown, taking next document...")
            web_doc.set_document_state("ERROR")
            web_doc.set_document_state_error("TEXT_TO_MD_ERROR")
            web_doc.save()
            continue

        web_doc.set_document_state("TEXT_TO_MD_DONE")
        web_doc.save()

        logger.info("Step 2: taking article content from markdown (ignoring portal links, disclaimers, user comments etc")
        logger.debug("Taking URL from database")
        logger.debug(f"URL: {web_doc.url}\n")

        metadata["url"] = web_doc.url

        found_rules = False
        regexp_rules_file = None
        extracted_text: str = ""
        for page_rules in page_regexp_map:
            if web_doc.url.find(page_rules) != -1:
                logger.debug("I found rules for this page, let's check if they are working")
                # pprint(page_regexp_map[page_rules])

                for rules_file in page_regexp_map[page_rules]:
                    logger.debug(f"Checking file: {rules_file}")
                    regexp_page = load_regex_from_file(rules_file)
                    # print(f"TRACE: regexp_page: {regexp_page}")
                    match = re.search(regexp_page, markdown_text, re.VERBOSE | re.DOTALL)

                    if match:
                        logger.debug(f"Regex defined in {rules_file} for finding article body is working.")
                        groups = match.groupdict()

                        if 'before' in groups:
                            pprint(match.group('before'))

                        if 'author' in groups and match.group('author'):
                            print("autor:>" + match.group('author').strip() + "<")
                        if 'created' in groups and match.group('created'):
                            print("created:" + match.group('created'))
                        if 'updated' in groups and match.group('updated'):
                            print("aktualizacja:" + match.group('updated'))
                        if 'title' in groups and match.group('title'):
                            print("tytuł:" + match.group('title'))

                        extracted_text = match.group('article_text').strip() if match else "Nie znaleziono treści"
                        found_rules = True
                        regexp_rules_file = rules_file
                        # exit(0)
                        break
                    else:
                        logger.debug(f"Nie znaleziono dopasowania z regułami z pliku {rules_file}.")
                        web_doc.set_document_state("ERROR")
                        web_doc.set_document_state_error("REGEX_ERROR")
                        web_doc.save()
                        continue

        if not found_rules:
            logger.error(f"Can't find rules to analyze page {web_doc.url}, time to check next one...")

            if find_problems:
                exit(1)

            if interactive:
                print("Naciśnij Enter, aby zakończyć program...")
                input()

            web_doc.set_document_state("ERROR")
            web_doc.set_document_state_error("REGEX_ERROR")
            web_doc.save()
            continue

        logger.debug(f"DEBUG: will use regex rule file: {regexp_rules_file}")
        metadata["regexp_rules_file"] = regexp_rules_file

        with open(cache_file_step_2_md, 'w', encoding="utf-8") as file:
            file.write(extracted_text)

        web_doc.set_document_state("MD_SIMPLIFIED")
        web_doc.save()

        if text_to_md_check_only:
            continue

        markdown = extracted_text

        logger.info("Changing windows line breaks to linux")
        markdown = re.sub(r'\r\n', '\n', markdown)

        with open(f"{cache_dir}/{document_id}_step_2_2_linux_eol.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.info("\nStep 3 - correcting links multiline issue")

        logger.debug(" Putting links into one line")
        markdown = links_correct(markdown)
        with open(f"{cache_dir}/{document_id}_step_3_1_links_one_line.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.debug(" Putting square brackets into one line")
        markdown = md_square_brackets_in_one_line(markdown)
        with open(f"{cache_dir}/{document_id}_step_3_2_square_brackets_one_line.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.info("\nStep 4 - converting markdown to text and creating metadata part for links and images")

        markdown, metadata["images_links"], metadata["links_as_images"] = md_get_images_as_links(markdown)
        logger.debug("4.0 Extracting images as links from markdown")
        with open(f"{cache_dir}/{document_id}_step_4_0_without_links_as_images.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.debug("4.1 Extracting images from markdown")
        markdown, metadata["images"] = get_images_with_links_md(markdown)

        with open(f"{cache_dir}/{document_id}_step_4_1_without_images.md", 'w', encoding="utf-8") as file:
            file.write(markdown)

        logger.debug("Removing NBSP from markdown")
        markdown = markdown.replace(' ', ' ')

        logger.debug("Formating text by removing multiple empty lines and spaces")
        # new_markdown = re.sub('\n+', '\n', new_markdown)
        markdown = re.sub(' +', ' ', markdown)
        markdown = re.sub(r'\n*##', '\n\n##', markdown)

        logger.debug("Removing links from markdown and adding into metadata part")
        markdown, metadata["links"] = process_markdown_and_extract_links(markdown)

        with open(f"{cache_dir}/{document_id}_step_4_2_without_links.md", 'w', encoding="utf-8") as file:
            logger.debug("Writing markdown to file from step 4")
            file.write(markdown)

        logger.info("\nStep 5: cleaning text for each big portal from external links inside text (not needed for embedding)")

        logger.debug("Onet: Extracting links with images from markdown")
        output_json = onet_see_also_process_markdown_and_extract_links_with_images(markdown)
        metadata["links_onet"] = output_json['links']
        markdown = output_json['markdown']

        logger.debug("Removing info strings")
        markdown = markdown.replace("*Dalsza część artykułu pod materiałem wideo*", "")

        if web_doc.url.startswith("https://www.onet.pl/") or web_doc.url.startswith("https://wiadomosci.onet.pl/"):
            logger.info("Removing info strings for onet.pl")

            markdown = re.sub(r"^\s+\*\s+\*\*Tekst\spublikujemy\sdzięki\suprzejmości\sserwisu.*$", "", markdown, flags=re.MULTILINE)

            linie = markdown.splitlines()
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
            markdown = "\n".join(wynik)

            # wiadomosci.onet.pl
            markdown = re.sub(r'^\*\*CZYTAJ\sWIĘCEJ:.*$', '', markdown, flags=re.MULTILINE)
            markdown = re.sub(r'^Kontynuuj\sczytanie\sod\smiejsca,\sw\sktórym\sskończyłeś\.$', '', markdown, flags=re.MULTILINE)
            #  ;)  ;)  ‹ wróć
            # markdown = re.sub(r'^.*;\).*;\).*\s+‹\swróć\s*$', '', markdown, flags=re.MULTILINE)
            # match = re.search(r'^(.*);\)(.*);\)(.*)\s+‹\swróć\s*$', markdown, re.MULTILINE)
            # if match:
            #     print("wiadomosci.onet.pl, match:")
            #     print(f">{match.group(1)}<")
            #     print(f">{match.group(2)}<")
            #     print(f">{match.group(3)}<")

            markdown = re.sub(r'^\s\*\s\*\*Przeczytaj:\*\*.*$', '', markdown, flags=re.MULTILINE)
            markdown = re.sub(r'^\s\*\s\*\*Przeczytaj\stakże:\*\*.*$', '', markdown, flags=re.MULTILINE)

            markdown = re.sub(r'^\s\*\s\*\*Czytaj\swięcej:\*\*.*$', '', markdown, flags=re.MULTILINE)

            markdown = re.sub(r'^\s\*\s\*\*Zobacz:\*\*.*$', '', markdown, flags=re.MULTILINE)
            markdown = re.sub(r'^\s\*\s\*\*Zobacz\stakże:\*\*.*$', '', markdown, flags=re.MULTILINE)
            markdown = re.sub(r'^\s\*\s\*\*Zobacz\srównież:\*\*.*$', '', markdown, flags=re.MULTILINE)
            markdown = re.sub(r"^\*\s\*\*.*?\*\*", "", markdown, flags=re.MULTILINE)
            markdown = re.sub(r"^##\sZobacz\srównież$", "", markdown, flags=re.MULTILINE)
            markdown = re.sub(r"^\s\*\sDużo\sczytania,\sa\smało\sczasu\?\sSprawdź\sskrót\sartykułu\s*$", "", markdown, flags=re.MULTILINE)

            markdown = re.sub(r"^\s*reklama\s*\n", "", markdown, flags=re.MULTILINE | re.DOTALL)


            markdown = re.sub(r"s*reklama$", "", markdown)


            markdown = re.sub(r"^\s+\* link\[\d+\]:.*$", "", markdown, flags=re.MULTILINE)

            markdown = re.sub(r"^\*\s\*\*.*?\*\*", "", markdown, flags=re.MULTILINE)

            markdown = re.sub(r'^\s*Dalszy\sciąg\smateriału\spod\swideo\s*$', '', markdown, flags=re.MULTILINE)

            markdown = re.sub(r'^\*\*Zobacz także:\*\*.*$', '', markdown, flags=re.MULTILINE)

        with open(f"{cache_dir}/{document_id}_step_5_without_portal_adding.md", 'w', encoding="utf-8") as file:
            logger.debug("Writing markdown to file from step 5")
            file.write(markdown)

        logger.debug("Writing final metadata file")
        with open(f"{cache_dir}/{document_id}_metadata.json", 'w', encoding="utf-8") as file:
            file.write(json.dumps(metadata, indent=4))


        logger.debug("Step 6: cleaning markdown document for embedding")

        logger.debug("Removing img from markdown")
        markdown = re.sub(r"picture\(\d+\):.*", '', markdown)

        logger.debug("Removing links from markdown")
        markdown = re.sub(r"link\[\d+]:", '', markdown)

        markdown = re.sub(r'\*\*', '', markdown)


        markdown = re.sub(r'^\s+$', '\n', markdown)

        # from unknown reason below code doesnt' work
        markdown = re.sub(r'^>\s', '', markdown, re.MULTILINE)
        # TODO: repalce with better code:
        lines = markdown.splitlines()
        lines2 = []
        for line in lines:
            if line.startswith("> "):
                line = line.replace("> ", "")
            lines2.append(line)
        markdown = "\n".join(lines2)

        markdown = re.sub(r'\*\*\n+\s*', '**\n', markdown)

        markdown = re.sub('\n{3,10}', '\n\n', markdown)

        with open(f"{cache_dir}/{document_id}_step_6.md", "w", encoding="utf-8") as f:
            f.write(markdown)

        logger.info(f"Raw text has {len(markdown.split())} words")
        parts = md_split_for_emb(markdown)
        logger.info(f"Text has been split into {len(parts)} parts")

        print("\n>FINAL DATA<\n")
        print(f"used a regule file: {regexp_rules_file}")
        parts_embeddings = []
        for i, part in enumerate(parts):
            print("\n####")
            print(f"part {i+1} has {len(part.split())} words")
            print(">Tekst before cleaning:")
            print(part)
            print(">Tekst after cleaning:")
            part = md_remove_markdown(part).strip()
            print(part)
            parts_embeddings.append(part)

        if interactive:
            print("Naciśnij Enter, aby zakończyć program...")
            input()

        if embedding_update:
            embedds = sherlock_create_embeddings(parts_embeddings)
            logger.info(f"Status code from embedding function: {embedds.status_code}")

            if not web_doc.language:
                web_doc.language = 'pl'

            for embedd in embedds.embedding:
                web_doc.embedding_add_simple("BAAI/bge-multilingual-gemma2", embedd["embedding"], parts[embedd["index"]])

        #     wb_db = WebsitesDBPostgreSQL()
        #     web_doc = StalkerWebDocumentDB(document_id=document_id)
        #     web_doc.embedding_add_by_parts(model=EMBEDDING_MODEL, parts=parts_txt)
        #     web_doc.text_md = markdown_text
        #     web_doc.text = markdown_to_text(markdown_text)
        #     web_doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST
        #     web_doc.save()

exit(0)
