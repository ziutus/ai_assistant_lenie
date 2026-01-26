#!/usr/bin/env python3
"""
Script to rename journal files to include the day of the week in English
"""
import os
import sys
from pathlib import Path
from datetime import datetime
import re
import io
import json

import requests
from markitdown import MarkItDown
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Add parent directory to path to import from library
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from library.website.website_download_context import webpage_raw_parse

JOURNAL_DIR = r"C:\Users\ziutus\Obsydian\personal\Journal"
TMP_DIR = "tmp"

TARGET_CONTENT = "# DONE"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}


def extract_json_ld(html_content: str) -> dict:
    """
    Extract JSON-LD structured data from HTML content.

    Args:
        html_content: HTML content as string

    Returns:
        Dictionary with extracted metadata or empty dict if not found
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        json_ld_scripts = soup.find_all('script', type='application/ld+json')

        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                # Handle @graph structure (Storytel uses this)
                if isinstance(data, dict) and '@graph' in data:
                    graph = data['@graph']
                    if isinstance(graph, list) and len(graph) > 0:
                        return graph[0]  # Return first item from graph
                # Return first valid JSON-LD we find
                elif isinstance(data, dict) and '@type' in data:
                    return data
                # Handle arrays of JSON-LD objects
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and '@type' in item:
                            return item
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON-LD: {e}")
                continue

        return {}
    except Exception as e:
        print(f"Error extracting JSON-LD: {e}")
        return {}


def format_storytel_metadata(json_ld: dict, url: str = "") -> str:
    """
    Format Storytel metadata from JSON-LD into readable markdown.

    Args:
        json_ld: Dictionary with JSON-LD data
        url: Original URL (used if not in JSON-LD)

    Returns:
        Formatted markdown string with metadata
    """
    if not json_ld:
        return ""

    metadata = []

    # Title (using 'name' from JSON-LD)
    if 'name' in json_ld:
        metadata.append(f"# {json_ld['name']}")
        metadata.append("")

    # URL
    if url:
        metadata.append(f"**URL:** {url}")
        metadata.append("")

    # Author(s)
    if 'author' in json_ld:
        authors = json_ld['author']
        if isinstance(authors, list):
            author_names = [a.get('name', a) if isinstance(a, dict) else str(a) for a in authors]
            metadata.append(f"**Autor:** {', '.join(author_names)}")
        elif isinstance(authors, str):
            metadata.append(f"**Autor:** {authors}")
        metadata.append("")

    # Narrator (readBy in Storytel JSON-LD)
    if 'readBy' in json_ld:
        narrators = json_ld['readBy']
        if isinstance(narrators, list):
            narrator_names = [n.get('name', n) if isinstance(n, dict) else str(n) for n in narrators]
            metadata.append(f"**Z:** {', '.join(narrator_names)}")
        elif isinstance(narrators, str):
            metadata.append(f"**Z:** {narrators}")
        metadata.append("")

    # Publisher
    if 'publisher' in json_ld:
        publisher = json_ld['publisher']
        if isinstance(publisher, dict):
            metadata.append(f"**Wydawca:** {publisher.get('name', '')}")
        elif isinstance(publisher, str):
            metadata.append(f"**Wydawca:** {publisher}")
        metadata.append("")

    # Publication date and format
    if 'datePublished' in json_ld:
        book_format = json_ld.get('bookFormat', 'Audiobook')
        metadata.append(f"**Wydanie:** {book_format}: {json_ld['datePublished']}")
        metadata.append("")

    # ISBN
    if 'isbn' in json_ld:
        metadata.append(f"**ISBN:** {json_ld['isbn']}")
        metadata.append("")

    # Language
    if 'inLanguage' in json_ld:
        lang_code = json_ld['inLanguage']
        lang_map = {'pl': 'pl', 'en': 'en', 'de': 'de', 'fr': 'fr', 'es': 'es'}
        lang_display = lang_map.get(lang_code, lang_code)
        metadata.append(f"**Język:** {lang_display}")
        metadata.append("")

    # Rating
    if 'aggregateRating' in json_ld:
        rating = json_ld['aggregateRating']
        if isinstance(rating, dict):
            rating_value = rating.get('ratingValue', '')
            rating_count = rating.get('ratingCount', '')
            metadata.append(f"**Ocena:** {rating_value}/5 ({rating_count} ocen)")
            metadata.append("")

    # Book format
    if 'bookFormat' in json_ld:
        metadata.append(f"**Format:** {json_ld['bookFormat']}")
        metadata.append("")

    # Description
    if 'description' in json_ld:
        metadata.append("## Opis")
        metadata.append("")
        metadata.append(json_ld['description'])
        metadata.append("")

    # Cover image
    if 'image' in json_ld:
        metadata.append(f"![Okładka]({json_ld['image']})")
        metadata.append("")

    return "\n".join(metadata)


def convert_html_to_markdown(mdit: MarkItDown, html_bytes: bytes, url: str) -> str:
    try:
        result = mdit.convert_stream(io.BytesIO(html_bytes), file_extension=".html", url=url)
        markdown_content = result.text_content or ""
    except Exception as e:
        print(f"Markdown conversion failed for {url}: {e}")
        markdown_content = ""

    if not markdown_content.strip():
        try:
            parsed = webpage_raw_parse(url, html_bytes, analyze_content=True)
            markdown_content = parsed.text or ""
        except Exception as e:
            print(f"Fallback HTML parse failed for {url}: {e}")

    return markdown_content


def clean_journal_files(dry_run=True):
    """
    Remove files that contain only '# DONE'

    Args:
        dry_run: If True, only print what would be deleted without actually deleting
    """
    journal_path = Path(JOURNAL_DIR)

    if not journal_path.exists():
        print(f"Directory does not exist: {JOURNAL_DIR}")
        return

    deleted_count = 0

    for file_path in journal_path.rglob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8").strip()

            if content == TARGET_CONTENT:
                if dry_run:
                    print(f"Would delete: {file_path}")
                else:
                    file_path.unlink()
                    print(f"Deleted: {file_path}")
                deleted_count += 1

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    if dry_run:
        print(f"\nDry run: {deleted_count} files would be deleted")
        print("Run with dry_run=False to actually delete files")
    else:
        print(f"\nDeleted {deleted_count} files")



def clean_storytel_links(dry_run=True):
    """
    Remove UTM parameters from Storytel links in journal files.

    Args:
        dry_run: If True, only print what would be changed without actually modifying files
    """
    journal_path = Path(JOURNAL_DIR)

    if not journal_path.exists():
        print(f"Directory does not exist: {JOURNAL_DIR}")
        return

    # Pattern to match Storytel links with UTM parameters
    storytel_pattern = re.compile(
        r'(https://storytel\.com/[^\s\)]*?)\?utm_source=internal&utm_medium=app_link&utm_campaign=share_links'
    )

    modified_count = 0
    total_replacements = 0

    for file_path in journal_path.rglob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")

            # Find and replace Storytel links
            matches = storytel_pattern.findall(content)
            if matches:
                new_content = storytel_pattern.sub(r'\1', content)

                if dry_run:
                    print(f"\nWould modify: {file_path.name}")
                    for match in matches:
                        print(f"  Clean: {match}")
                else:
                    file_path.write_text(new_content, encoding="utf-8")
                    print(f"\nModified: {file_path.name}")
                    for match in matches:
                        print(f"  Cleaned: {match}")

                modified_count += 1
                total_replacements += len(matches)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    if dry_run:
        print(f"\nDry run: {total_replacements} links in {modified_count} files would be cleaned")
        print("Run with dry_run=False to actually modify files")
    else:
        print(f"\nCleaned {total_replacements} links in {modified_count} files")


def download_storytel_pages_with_playwright():
    """
    Download Storytel pages from journal files using Playwright and save as HTML and Markdown.
    Extracts metadata from JSON-LD structured data.
    """
    journal_path = Path(JOURNAL_DIR)
    tmp_path = Path(TMP_DIR)

    if not journal_path.exists():
        print(f"Directory does not exist: {JOURNAL_DIR}")
        return

    if not tmp_path.exists():
        tmp_path.mkdir(parents=True)
        print(f"Created tmp directory: {TMP_DIR}")

    # Pattern to match Storytel links (with or without UTM parameters)
    # Match URL until whitespace, closing parenthesis, or end of line
    storytel_pattern = re.compile(
        r'https://storytel\.com/[^\s\)]*'
    )

    downloaded_count = 0
    urls_found = set()

    # First pass: collect all unique Storytel URLs
    for file_path in journal_path.rglob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            matches = storytel_pattern.findall(content)

            for match in matches:
                # Clean URL from UTM parameters
                clean_url = re.sub(
                    r'\?utm_source=internal&utm_medium=app_link&utm_campaign=share_links',
                    '',
                    match
                )
                urls_found.add(clean_url)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    print(f"\nFound {len(urls_found)} unique Storytel URLs")

    # Initialize MarkItDown converter once before the loop
    mdit = MarkItDown()

    # Use Playwright to download pages
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale='pl-PL',
            user_agent=DEFAULT_HEADERS["User-Agent"]
        )
        page = context.new_page()

        # Second pass: download each URL
        for url in sorted(urls_found):
            try:
                # Extract book ID from URL for filename
                book_id_match = re.search(r'/books/[^/]+-(\d+)', url)
                if not book_id_match:
                    print(f"Could not extract book ID from URL: {url}")
                    continue

                book_id = book_id_match.group(1)
                html_file = tmp_path / f"storytel_{book_id}.html"
                md_file = tmp_path / f"storytel_{book_id}.md"
                json_file = tmp_path / f"storytel_{book_id}.json"

                # Skip if already downloaded
                if html_file.exists() and md_file.exists() and json_file.exists():
                    print(f"Already downloaded: {book_id}")
                    continue

                try:
                    # Download page with Playwright
                    print(f"Downloading with Playwright: {url}")
                    page.goto(url, wait_until="networkidle", timeout=30000)

                    # Get HTML content
                    html_content = page.content()

                    # Save HTML
                    html_file.write_text(html_content, encoding="utf-8")
                    print(f"Saved HTML: {html_file}")

                    # Extract JSON-LD metadata
                    json_ld = extract_json_ld(html_content)

                    if json_ld:
                        # Save JSON-LD
                        json_file.write_text(json.dumps(json_ld, indent=2, ensure_ascii=False), encoding="utf-8")
                        print(f"Saved JSON-LD metadata: {json_file}")

                        # Format metadata as markdown
                        metadata_md = format_storytel_metadata(json_ld, url)
                    else:
                        print(f"Warning: No JSON-LD metadata found for {url}")
                        metadata_md = ""

                    # Save Markdown with metadata only (no full HTML conversion)
                    md_file.write_text(metadata_md, encoding="utf-8")
                    print(f"Saved Markdown: {md_file}")

                    downloaded_count += 1

                except Exception as e:
                    print(f"Error downloading {url}: {e}")

            except Exception as e:
                print(f"Error processing {url}: {e}")

        browser.close()

    print(f"\nDownloaded {downloaded_count} new Storytel pages")


def download_storytel_pages():
    """
    Download Storytel pages from journal files and save as HTML and Markdown.
    Uses requests library (legacy method).
    """
    journal_path = Path(JOURNAL_DIR)
    tmp_path = Path(TMP_DIR)

    if not journal_path.exists():
        print(f"Directory does not exist: {JOURNAL_DIR}")
        return

    if not tmp_path.exists():
        tmp_path.mkdir(parents=True)
        print(f"Created tmp directory: {TMP_DIR}")

    # Pattern to match Storytel links (with or without UTM parameters)
    # Match URL until whitespace, closing parenthesis, or end of line
    storytel_pattern = re.compile(
        r'https://storytel\.com/[^\s\)]*'
    )

    downloaded_count = 0
    urls_found = set()

    # First pass: collect all unique Storytel URLs
    for file_path in journal_path.rglob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            matches = storytel_pattern.findall(content)

            for match in matches:
                # Clean URL from UTM parameters
                clean_url = re.sub(
                    r'\?utm_source=internal&utm_medium=app_link&utm_campaign=share_links',
                    '',
                    match
                )
                urls_found.add(clean_url)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    print(f"\nFound {len(urls_found)} unique Storytel URLs")

    # Initialize MarkItDown converter once before the loop
    mdit = MarkItDown()

    # Second pass: download each URL
    for url in sorted(urls_found):
        try:
            # Extract book ID from URL for filename
            book_id_match = re.search(r'/books/[^/]+-(\d+)', url)
            if not book_id_match:
                print(f"Could not extract book ID from URL: {url}")
                continue

            book_id = book_id_match.group(1)
            html_file = tmp_path / f"storytel_{book_id}.html"
            md_file = tmp_path / f"storytel_{book_id}.md"

            # Skip if already downloaded
            if html_file.exists() and md_file.exists():
                print(f"Already downloaded: {book_id}")
                continue

            try:
                # Download HTML
                print(f"Downloading: {url}")
                response = requests.get(url, timeout=30, headers=DEFAULT_HEADERS)
                response.raise_for_status()

                # Save HTML
                html_file.write_bytes(response.content)
                print(f"Saved HTML: {html_file}")

                markdown_content = convert_html_to_markdown(mdit, response.content, url)

                # Save Markdown
                md_file.write_text(markdown_content, encoding="utf-8")
                print(f"Saved Markdown: {md_file}")

                downloaded_count += 1

            except Exception as e:
                print(f"Error downloading {url}: {e}")

        except Exception as e:
            print(f"Error processing {url}: {e}")

    print(f"\nDownloaded {downloaded_count} new Storytel pages")


def add_weekday_to_filenames(dry_run=True):
    """
    Rename files in format YYYY-MM-DD.md to YYYY-MM-DD-Weekday.md

    Args:
        dry_run: If True, only print what would be renamed without actually renaming
    """
    journal_path = Path(JOURNAL_DIR)

    if not journal_path.exists():
        print(f"Directory does not exist: {JOURNAL_DIR}")
        return

    # Pattern for files without weekday: YYYY-MM-DD.md or YYYY MM DD.md
    pattern_dash = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
    pattern_space = re.compile(r"^(\d{4}) (\d{2}) (\d{2})\.md$")
    # Pattern for files with weekday: YYYY-MM-DD-Weekday.md
    pattern_with_weekday = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-[A-Za-z]{3}\.md$")

    renamed_count = 0

    for file_path in journal_path.rglob("*.md"):
        filename = file_path.name
        match = pattern_dash.match(filename) or pattern_space.match(filename) or pattern_with_weekday.match(filename)

        if match:
            try:
                year, month, day = match.groups()

                # Fix year 2024 -> 2025
                if year == "2024":
                    year = "2025"

                date = datetime(int(year), int(month), int(day))
                weekday = date.strftime("%a")  # 3-letter weekday abbreviation in English

                new_filename = f"{year}-{month}-{day}-{weekday}.md"
                new_path = file_path.parent / new_filename

                # Check if target file already exists
                if new_path.exists() and new_path != file_path:
                    print(f"Skipping {filename}: target file {new_filename} already exists")
                    continue

                if dry_run:
                    print(f"Would rename: {filename} -> {new_filename}")
                else:
                    file_path.rename(new_path)
                    print(f"Renamed: {filename} -> {new_filename}")
                renamed_count += 1

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    if dry_run:
        print(f"\nDry run: {renamed_count} files would be renamed")
        print("Run with dry_run=False to actually rename files")
    else:
        print(f"\nRenamed {renamed_count} files")


if __name__ == "__main__":
    # Download Storytel pages from journal files using Playwright and JSON-LD parsing
    download_storytel_pages_with_playwright()

    # Other available functions:
    # download_storytel_pages()  # Legacy method using requests
    # clean_storytel_links(dry_run=True)
    # add_weekday_to_filenames(dry_run=False)
    # clean_journal_files(dry_run=True)
