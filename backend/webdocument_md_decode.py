import argparse
import os.path
import re
import json
import logging
from pprint import pprint

from library.api.cloudferro.sherlock.sherlock_embedding import sherlock_create_embeddings
from library.article_pipeline import ensure_raw_markdown
from library.document_prepare import calculate_reduction
from library.lenie_markdown import get_images_with_links_md, links_correct, process_markdown_and_extract_links, \
    md_square_brackets_in_one_line, md_split_for_emb, md_get_images_as_links, md_remove_markdown
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.db.engine import get_session
from library.db.models import Document
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.config_loader import load_config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

cfg = load_config()


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

# Linie-śmieci portalu onet.pl usuwane w całości (re.MULTILINE).
# Wzorce operują na markdownie PO ekstrakcji linków/obrazków (markery link[N]:)
# — to inny etap niż library/article_cleaner, który czyści tekst z markerami [linkN].
_ONET_LINE_PATTERNS = [
    r"^\s+\*\s+\*\*Tekst\spublikujemy\sdzięki\suprzejmości\sserwisu.*$",
    r"^\*\*CZYTAJ\sWIĘCEJ:.*$",
    r"^Kontynuuj\sczytanie\sod\smiejsca,\sw\sktórym\sskończyłeś\.$",
    # " * **Przeczytaj:**", " * **Zobacz także:**", " * **Czytaj więcej:**" itp.
    r"^\s\*\s\*\*(?:Przeczytaj|Przeczytaj\stakże|Czytaj\swięcej|Zobacz|Zobacz\stakże|Zobacz\srównież):\*\*.*$",
    r"^\*\s\*\*.*?\*\*",
    r"^##\sZobacz\srównież$",
    r"^\s\*\sDużo\sczytania,\sa\smało\sczasu\?\sSprawdź\sskrót\sartykułu\s*$",
    r"^\s+\* link\[\d+\]:.*$",
    r"^\s*Dalszy\sciąg\smateriału\spod\swideo\s*$",
    r"^\*\*Zobacz także:\*\*.*$",
]


def clean_onet_artifacts(markdown: str) -> str:
    """Usuń śmieci portalowe onet.pl (CZYTAJ WIĘCEJ, reklama, itp.) z markdownu."""
    # Pusta linia przed liniami **bold** i nagłówkami ## (czytelność po sklejeniu)
    lines_out = []
    for line in markdown.splitlines():
        if (line.startswith("**") and line.endswith("**")) or line.startswith("## "):
            if lines_out and lines_out[-1] != '\n':
                lines_out.append("")
        lines_out.append(line)
    markdown = "\n".join(lines_out)

    for pattern in _ONET_LINE_PATTERNS:
        markdown = re.sub(pattern, "", markdown, flags=re.MULTILINE)

    markdown = re.sub(r"^\s*reklama\s*\n", "", markdown, flags=re.MULTILINE | re.DOTALL)
    markdown = re.sub(r"\s*reklama\s*$", "", markdown)
    return markdown


def load_regex_from_file(file_path):
    """
    Funkcja wczytująca wyrażenie regularne z zewnętrznego pliku.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Plik z regułami nie został znaleziony: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        logger.debug(f"Lead_regx_from_file: reading file: {file_path} ")
        return f.read().strip()


cache_dir_base = os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown")


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
    "https://biznes.interia.pl/": [
        "data/pages_analyze/interia_pl_7730.regex",
        "data/pages_analyze/interia_pl_7456.regex",
    ],
    "https://geekweek.interia.pl": [
        "data/pages_analyze/geekweek_interia_pl_6837.regex",
        "data/pages_analyze/geekweek_interia_pl_7785.regex",
        "data/pages_analyze/geekweek_interia_pl_7687.regex",
    ],
     "https://www.o2.pl/": [
         "data/pages_analyze/o2_pl_1.regex",
         "data/pages_analyze/o2_pl_2.regex",
         "data/pages_analyze/o2_pl_3.regex",
     ]
    # "": []
}

page_rules_map = {
    "https://www.money.pl": ["data/pages_rules/money.rules"]
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Extract article text from webpage markdown (regexp rules + LLM fallback), "
                    "clean it and optionally create embeddings.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--url-prefix",
                           help='Process documents whose URL starts with prefix, e.g. "https://biznes.interia.pl/"')
    selection.add_argument("--ids", type=int, nargs="+", metavar="ID",
                           help="Explicit document IDs to process")
    parser.add_argument("--interactive", action="store_true",
                        help="Pause for Enter after each document")
    parser.add_argument("--find-problems", action="store_true",
                        help="Exit immediately when neither regex rules nor LLM fallback match")
    parser.add_argument("--md-check-only", action="store_true",
                        help="Stop after article extraction (skip link/image processing and embeddings)")
    parser.add_argument("--embedding-update", action="store_true",
                        help="Create and store embeddings for the cleaned parts")
    parser.add_argument("--skip-regex-errors", action="store_true",
                        help="Skip documents already marked with REGEX_ERROR")
    parser.add_argument("--no-llm-fallback", action="store_true",
                        help="Disable LLM fallback when regex rules do not match")
    parser.add_argument("--llm-model", default="speakleash/Bielik-11B-v3.0-Instruct",
                        help="LLM model for fallback extraction")
    args = parser.parse_args()

    interactive = args.interactive
    find_problems = args.find_problems
    text_to_md_check_only = args.md_check_only
    embedding_update = args.embedding_update
    ignore_regexp_issue = not args.skip_regex_errors
    llm_fallback_enabled = not args.no_llm_fallback
    llm_fallback_model = args.llm_model

    session = get_session()
    wb_db = WebsitesDBPostgreSQL(session=session)

    # TODO: 7683 - need to correct related liks
    # TODO: 7741 - udostępnij artykuł - linki do ustąpienia do regexp: businessinsider_com_pl_2025_1.regex
    # TODO: 7732 - lepszy podział na części do embeddingu
    # TODO: 7687 - poprawić regexp geekweek_interia_pl_7687.regex
    if args.ids:
        documents = args.ids
    else:
        documents = wb_db.get_documents_by_url(args.url_prefix)

    try:
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
            doc = Document.get_by_id(session, document_id)
            if doc is None:
                logger.warning(f"Document {document_id} not found, skipping")
                continue

            if doc.document_state == StalkerDocumentStatus.ERROR.name and doc.document_state_error == StalkerDocumentStatusError.ERROR_DOWNLOAD.name:
                logger.info("Ignoring document as is error is ERROR_DOWNLOAD...")
                continue

            cache_dir = os.path.join(cache_dir_base, str(document_id))
            if not os.path.exists(cache_dir):
                logger.debug(f"Creating cache directory {cache_dir}")
                os.makedirs(cache_dir)

            if doc.document_state_error == StalkerDocumentStatusError.REGEX_ERROR.name and not ignore_regexp_issue:
                logger.info("Ignoring document as is REGEX_ERROR, to work on it, change ignore_regexp_issue to 'True'")
                continue

            metadata = {"document_id": document_id}
            cache_file_html = os.path.join(cache_dir, f"{document_id}.html")
            cache_file_step_2_md = os.path.join(cache_dir, f"{document_id}_step_2_1_article.md")

            logger.info("Step 1: preparing markdown from HTML file")
            # Reads step_1 from cache; otherwise downloads HTML (cache/S3),
            # converts via the MarkItDown -> html2markdown -> html2text cascade
            # and persists {id}_step_1_all.md (library/article_pipeline).
            markdown_text = ensure_raw_markdown(doc, cache_dir, verbose=False)
            if not markdown_text:
                logger.debug("Can't get markdown (no uuid or HTML not in cache/S3), skipping...")
                continue

            # Quality gate: a sane conversion shrinks HTML by 30-98%.
            # Only checkable when the HTML file is present in cache (it is not
            # when markdown came straight from a cached step_1/md file).
            if os.path.isfile(cache_file_html):
                html_size = os.path.getsize(cache_file_html)
                reduction_percentage = calculate_reduction(html_size, len(markdown_text))
                logger.debug(f"HTML size: {html_size} B, markdown reduction: {reduction_percentage:.2f}%")
                if reduction_percentage < 30 or reduction_percentage >= 98:
                    logger.error("ERROR: Something wrong with transformation to markdown, taking next document...")
                    doc.document_state = StalkerDocumentStatus.ERROR.name
                    doc.document_state_error = StalkerDocumentStatusError.TEXT_TO_MD_ERROR.name
                    session.commit()
                    continue

            doc.document_state = StalkerDocumentStatus.NEED_CLEAN_MD.name
            session.commit()

            logger.info("Step 2: taking article content from markdown (ignoring portal links, disclaimers, user comments etc")
            logger.debug("Taking URL from database")
            logger.debug(f"URL: {doc.url}\n")

            metadata["url"] = doc.url

            found_rules = False
            regexp_rules_file = None
            extracted_text: str = ""
            for page_rules in page_regexp_map:
                if doc.url.find(page_rules) != -1:
                    logger.debug("I found rules for this page, let's check if they are working")

                    for rules_file in page_regexp_map[page_rules]:
                        logger.debug(f"Checking file: {rules_file}")
                        regexp_page = load_regex_from_file(rules_file)
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
                            break
                        else:
                            logger.debug(f"Nie znaleziono dopasowania z regułami z pliku {rules_file}.")
                            doc.document_state = StalkerDocumentStatus.ERROR.name
                            doc.document_state_error = StalkerDocumentStatusError.REGEX_ERROR.name
                            session.commit()
                            continue

            if not found_rules:
                logger.error(f"Can't find rules to analyze page {doc.url}, trying LLM fallback...")

                if llm_fallback_enabled:
                    from library.article_extractor import process_article_with_llm_fallback
                    llm_result = process_article_with_llm_fallback(
                        markdown_text=markdown_text,
                        document_id=document_id,
                        cache_dir=cache_dir,
                        url=doc.url,
                        model=llm_fallback_model,
                    )
                    if llm_result:
                        extracted_text = llm_result
                        found_rules = True
                        regexp_rules_file = "LLM_FALLBACK"
                        logger.info(f"LLM fallback succeeded for document {document_id}")
                    else:
                        logger.error(f"LLM fallback also failed for document {document_id}")

                if not found_rules:
                    if find_problems:
                        exit(1)

                    if interactive:
                        print("Naciśnij Enter, aby zakończyć program...")
                        input()

                    doc.document_state = StalkerDocumentStatus.ERROR.name
                    doc.document_state_error = StalkerDocumentStatusError.REGEX_ERROR.name
                    session.commit()
                    continue

            logger.debug(f"DEBUG: will use regex rule file: {regexp_rules_file}")
            metadata["regexp_rules_file"] = regexp_rules_file

            with open(cache_file_step_2_md, 'w', encoding="utf-8") as file:
                file.write(extracted_text)

            doc.document_state = StalkerDocumentStatus.MD_SIMPLIFIED.name
            session.commit()

            if text_to_md_check_only:
                continue

            markdown = extracted_text

            logger.info("Changing windows line breaks to linux")
            markdown = re.sub(r'\r\n', '\n', markdown)

            with open(os.path.join(cache_dir, f"{document_id}_step_2_2_linux_eol.md"), 'w', encoding="utf-8") as file:
                file.write(markdown)

            logger.info("\nStep 3 - correcting links multiline issue")

            logger.debug(" Putting links into one line")
            markdown = links_correct(markdown)
            with open(os.path.join(cache_dir, f"{document_id}_step_3_1_links_one_line.md"), 'w', encoding="utf-8") as file:
                file.write(markdown)

            logger.debug(" Putting square brackets into one line")
            markdown = md_square_brackets_in_one_line(markdown)
            with open(os.path.join(cache_dir, f"{document_id}_step_3_2_square_brackets_one_line.md"), 'w', encoding="utf-8") as file:
                file.write(markdown)

            logger.info("\nStep 4 - converting markdown to text and creating metadata part for links and images")

            markdown, metadata["images_links"], metadata["links_as_images"] = md_get_images_as_links(markdown)
            logger.debug("4.0 Extracting images as links from markdown")
            with open(os.path.join(cache_dir, f"{document_id}_step_4_0_without_links_as_images.md"), 'w', encoding="utf-8") as file:
                file.write(markdown)

            logger.debug("4.1 Extracting images from markdown")
            markdown, metadata["images"] = get_images_with_links_md(markdown)

            with open(os.path.join(cache_dir, f"{document_id}_step_4_1_without_images.md"), 'w', encoding="utf-8") as file:
                file.write(markdown)

            logger.debug("Removing NBSP from markdown")
            markdown = markdown.replace('\xa0', ' ')

            logger.debug("Formating text by removing multiple empty lines and spaces")
            markdown = re.sub(' +', ' ', markdown)
            markdown = re.sub(r'\n*##', '\n\n##', markdown)

            logger.debug("Removing links from markdown and adding into metadata part")
            markdown, metadata["links"] = process_markdown_and_extract_links(markdown)

            with open(os.path.join(cache_dir, f"{document_id}_step_4_2_without_links.md"), 'w', encoding="utf-8") as file:
                logger.debug("Writing markdown to file from step 4")
                file.write(markdown)

            logger.info("\nStep 5: cleaning text for each big portal from external links inside text (not needed for embedding)")

            logger.debug("Onet: Extracting links with images from markdown")
            output_json = onet_see_also_process_markdown_and_extract_links_with_images(markdown)
            metadata["links_onet"] = output_json['links']
            markdown = output_json['markdown']

            logger.debug("Removing info strings")
            markdown = markdown.replace("*Dalsza część artykułu pod materiałem wideo*", "")

            if doc.url.startswith("https://www.onet.pl/") or doc.url.startswith("https://wiadomosci.onet.pl/"):
                logger.info("Removing info strings for onet.pl")
                markdown = clean_onet_artifacts(markdown)

            with open(os.path.join(cache_dir, f"{document_id}_step_5_without_portal_adding.md"), 'w', encoding="utf-8") as file:
                logger.debug("Writing markdown to file from step 5")
                file.write(markdown)

            logger.debug("Writing final metadata file")
            with open(os.path.join(cache_dir, f"{document_id}_metadata.json"), 'w', encoding="utf-8") as file:
                file.write(json.dumps(metadata, indent=4))


            logger.debug("Step 6: cleaning markdown document for embedding")

            logger.debug("Removing img from markdown")
            markdown = re.sub(r"picture\[\d+\]:.*", '', markdown)

            logger.debug("Removing links from markdown")
            markdown = re.sub(r"link\[\d+]:", '', markdown)

            markdown = re.sub(r'\*\*', '', markdown)


            markdown = re.sub(r'^\s+$', '\n', markdown)

            # Note: 4th positional arg of re.sub is `count`, not `flags` — that was
            # why the old `re.sub(r'^>\s', '', markdown, re.MULTILINE)` "didn't work".
            markdown = re.sub(r'^>\s', '', markdown, flags=re.MULTILINE)

            markdown = re.sub(r'\*\*\n+\s*', '**\n', markdown)

            markdown = re.sub('\n{3,10}', '\n\n', markdown)

            with open(os.path.join(cache_dir, f"{document_id}_step_6.md"), "w", encoding="utf-8") as f:
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

                if not doc.language:
                    doc.language = 'pl'

                for embedd in embedds.embedding:
                    wb_db.embedding_add(
                        document_id=doc.id,
                        embedding=embedd["embedding"],
                        language=doc.language,
                        text=parts[embedd["index"]],
                        text_original=parts[embedd["index"]],
                        model="BAAI/bge-multilingual-gemma2",
                    )
                session.commit()

    finally:
        session.close()
