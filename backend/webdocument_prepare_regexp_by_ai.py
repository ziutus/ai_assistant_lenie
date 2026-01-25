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
from library.stalker_web_document import StalkerWebDocument
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.api.aws.s3_aws import s3_file_exist, s3_take_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

S3_BUCKET_NAME = os.getenv("AWS_S3_WEBSITE_CONTENT")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

wb_db = WebsitesDBPostgreSQL()

# cache dir for S3 downloads and markdown output
cache_dir_base = os.getenv("CACHE_DIR", "tmp/markdown")

def calculate_reduction(html_size, markdown_size):
    return ((html_size - markdown_size) / html_size) * 100

# regex for money.pl article extraction with author capture
# Use the first H1 as the article start and detect the footer blocks as the end.
MONEY_ARTICLE_REGEX_PRE = r'(?ms)^#\s+.+\n'
MONEY_ARTICLE_REGEX_POST = (
    r'(?ms)\n(?:\* \* \*\s*)?(?:\s*\n)*'
    r'(?:WALUTY __|KALKULATORY __|KREDYTY __|GIE'
    r'|MONEY NA SKR|MNIEJ TEMAT|Odkryj|Najnowsze)'
)

documents = [ 11618 ]

#documents = wb_db.get_documents_by_url("https://www.money.pl/")


pprint(documents)
for document_id in documents:
    web_doc_db = StalkerWebDocumentDB(document_id=document_id)

    if not web_doc_db.s3_uuid:
        logger.warning(f"document_id: {document_id} Missing s3_uuid, skipping")
        continue

    if not os.path.exists(cache_dir_base):
        os.makedirs(cache_dir_base)

    cache_dir = os.path.join(cache_dir_base, str(document_id))
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    cache_file_html = os.path.join(cache_dir, f"{document_id}.html")
    cache_file_md = os.path.join(cache_dir, f"{document_id}.md")
    cache_file_text = os.path.join(cache_dir, f"{document_id}.txt")

    if not os.path.isfile(cache_file_text):
        logger.info(f"document_id: {document_id} Text file does not exist: {cache_file_text}, skipping")
        continue

    # save information to json file in chache dir
    cache_file_info = os.path.join(cache_dir, f"{document_id}_info.json")
    doc_info = {
        "id": web_doc_db.id,
        "url": web_doc_db.url,
        "title": web_doc_db.title,
        "language": web_doc_db.language,
        "s3_uuid": web_doc_db.s3_uuid,
        "created_at": web_doc_db.created_at.strftime("%Y-%m-%d %H:%M:%S") if web_doc_db.created_at else None,
        "document_type": web_doc_db.document_type.name if web_doc_db.document_type else None,
        "document_state": web_doc_db.document_state.name if web_doc_db.document_state else None,
    }
    with open(cache_file_info, "w", encoding="utf-8") as f:
        json.dump(doc_info, f, ensure_ascii=False, indent=2)
    logger.info(f"document_id: {document_id} Document info saved to {cache_file_info}")

    if os.path.isfile(cache_file_md):
        logger.info(f"document_id: {document_id} Using cached markdown file: {cache_file_md}")
        with open(cache_file_md, "r", encoding="utf-8") as f:
            markdown_text = f.read()
    else:
        if not os.path.isfile(cache_file_html):
            logger.debug(f"document_id: {document_id} Downloading HTML file from S3")
            s3_key = f"{web_doc_db.s3_uuid}.html"
            if not s3_file_exist(S3_BUCKET_NAME, s3_key):
                logger.error(f"document_id: {document_id} HTML file not found in S3: {s3_key}")
                continue

            if not s3_take_file(S3_BUCKET_NAME, s3_key, cache_file_html):
                logger.error(f"document_id: {document_id} Failed to download HTML from S3: {s3_key}")
                continue

        logger.info(f"document_id: {document_id} Converting HTML to markdown")
        mdit = MarkItDown()
        result = mdit.convert(cache_file_html).text_content

        html_size = os.path.getsize(cache_file_html)
        md_size = len(result)
        reduction_percentage = calculate_reduction(html_size, md_size)
        markdown_text = result

        if reduction_percentage < 30:
            logger.debug(f"document_id: {document_id} MarkItDown reduction too small, trying html2markdown")
            with open(cache_file_html, "r", encoding="utf-8") as f:
                html = f.read()

            markdown = convert(html)
            md_size_2 = len(markdown)
            reduction_percentage = calculate_reduction(html_size, md_size_2)
            markdown_text = markdown

            if reduction_percentage < 30:
                logger.debug(f"document_id: {document_id} html2markdown reduction too small, trying html2text")
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = False
                markdown_text = h.handle(html)

        with open(cache_file_md, "w", encoding="utf-8") as f:
            f.write(markdown_text)
            logger.info(f"document_id: {document_id} Markdown saved to {cache_file_md}")

        web_doc_db.text_md = markdown_text
        web_doc_db.save()

    pre_match = re.search(MONEY_ARTICLE_REGEX_PRE, markdown_text)
    if not pre_match:
        logger.warning(f"document_id: {document_id} Money.pl regex PRE did not match the markdown content")
        continue

    post_match = re.search(MONEY_ARTICLE_REGEX_POST, markdown_text[pre_match.end():])
    if not post_match:
        logger.warning(f"document_id: {document_id} Money.pl regex POST did not match the markdown content")
        continue

    article_chunk = markdown_text[pre_match.end():pre_match.end() + post_match.start()]

    author_regex_link = (
        r'(?ms)\[(?P<author>[^\]]+)\]\(https?://www\.money\.pl/archiwum/autor/[^)]+\)\s*\n'
        r'(?:[^\n]*\n){0,6}?\s*\n(?P<article_text>\S[\s\S]*)'
    )
    author_regex_underscore = (
        r'(?ms)(?P<article_text>.*?\n_(?P<author>[^,_\n]+?)(?:,\s*(?P<author_desc>[^_\n]+))?_\s*)'
    )
    match = re.search(author_regex_link, article_chunk) or re.search(author_regex_underscore, article_chunk)
    if match:
        logger.info(f"document_id: {document_id} Money.pl author regex matched the markdown content")
        article_text = match.group("article_text").strip()
        author = match.group("author").strip()
        author = re.sub(r'^Rozmaw\\S+\\s+', '', author, flags=re.IGNORECASE)
        author_desc = match.groupdict().get("author_desc")
        author_desc = author_desc.strip() if author_desc else ""

        cache_file_article = os.path.join(cache_dir, f"{document_id}_article.md")
        with open(cache_file_article, "w", encoding="utf-8") as f:
            f.write(article_text)

        cache_file_author = os.path.join(cache_dir, f"{document_id}_author.json")
        with open(cache_file_author, "w", encoding="utf-8") as f:
            f.write(json.dumps({"author": author, "author_desc": author_desc}, ensure_ascii=False, indent=2))

        logger.info(f"document_id: {document_id} Article and author extracted to {cache_file_article}")
    else:
        logger.warning(f"document_id: {document_id} Money.pl author regex did not match the markdown content")
