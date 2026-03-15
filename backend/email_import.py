#!/usr/bin/env python3
"""CLI script for importing Gmail emails into Lenie AI.

Requires gws CLI (Google Workspace CLI) to be installed and authenticated:
    npm install -g @googleworkspace/cli
    gws auth setup

Usage:
    python email_import.py --search "subject:AI Flash #78"
    python email_import.py --id 19ce7076beeaf054
    python email_import.py --id 19ce7076beeaf054 --source "newsletter:AI Flash" --note "AI news digest"
    python email_import.py --search "from:campus@campusai.pl" --list
    python email_import.py --id 19ce7076beeaf054 --dry-run
"""

import argparse
import base64
import html
import json
import logging
import re
import subprocess
import sys
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import WebDocument  # noqa: E402
from library.models.stalker_document_status import StalkerDocumentStatus  # noqa: E402
from library.models.stalker_document_type import StalkerDocumentType  # noqa: E402

logger = logging.getLogger(__name__)


def _find_gws_binary() -> str:
    """Find the gws binary, accounting for Windows npm .cmd wrappers."""
    import shutil
    gws_path = shutil.which("gws")
    if gws_path:
        return gws_path
    # Windows: npm installs .cmd wrappers
    gws_cmd = shutil.which("gws.cmd")
    if gws_cmd:
        return gws_cmd
    raise FileNotFoundError("gws CLI not found. Install with: npm install -g @googleworkspace/cli")


def run_gws(args: list[str]) -> dict:
    """Run a gws CLI command and return parsed JSON output."""
    gws_bin = _find_gws_binary()
    cmd = [gws_bin] + args
    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"gws command failed: {result.stderr.strip()}")
    # gws prints "Using keyring backend: keyring" to stdout before JSON
    output = result.stdout.strip()
    # Find the first '{' or '[' to skip any preamble
    for i, ch in enumerate(output):
        if ch in ('{', '['):
            return json.loads(output[i:])
    raise RuntimeError(f"No JSON in gws output: {output[:200]}")


def search_emails(query: str, max_results: int = 10) -> list[dict]:
    """Search Gmail for messages matching a query. Returns list of {id, threadId}."""
    data = run_gws([
        "gmail", "users", "messages", "list",
        "--params", json.dumps({"userId": "me", "q": query, "maxResults": max_results}),
    ])
    return data.get("messages", [])


def get_email(msg_id: str) -> dict:
    """Fetch full email message by ID."""
    return run_gws([
        "gmail", "users", "messages", "get",
        "--params", json.dumps({"userId": "me", "id": msg_id}),
    ])


def extract_header(msg: dict, name: str) -> str | None:
    """Extract a header value from a Gmail message."""
    for header in msg.get("payload", {}).get("headers", []):
        if header["name"].lower() == name.lower():
            return header["value"]
    return None


def decode_body(data: str) -> str:
    """Decode base64url-encoded body data."""
    # Gmail uses URL-safe base64 without padding
    padded = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def find_body_part(payload: dict, mime_type: str) -> str | None:
    """Recursively find a body part with the given MIME type."""
    if payload.get("mimeType") == mime_type:
        body_data = payload.get("body", {}).get("data")
        if body_data:
            return decode_body(body_data)

    for part in payload.get("parts", []):
        result = find_body_part(part, mime_type)
        if result:
            return result
    return None


def is_tracking_url(url: str) -> bool:
    """Check if a URL looks like a newsletter tracking/redirect URL."""
    tracking_patterns = [
        r"emlnk\d*\.com/lt\.php",      # ActiveCampaign / CampusAI
        r"click\.\w+\.\w+/",           # Mailchimp, Sendinblue, etc.
        r"links\.\w+\.\w+/",           # Generic link trackers
        r"track\.\w+\.\w+/",           # Generic trackers
        r"email\.mg\.\w+/",            # Mailgun
        r"u\d+\.ct\.sendgrid\.net/",   # SendGrid
        r"r\.email\.",                  # Various ESPs
        r"mandrillapp\.com/track/",    # Mandrill
        r"/lt\.php\?",                 # Generic link tracker pattern
    ]
    return any(re.search(pattern, url) for pattern in tracking_patterns)


def strip_utm_params(url: str) -> str:
    """Remove UTM and other marketing query parameters from a URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    clean_params = {k: v for k, v in params.items()
                    if not k.startswith(("utm_", "mc_", "ss_", "vero_"))}
    clean_query = urlencode(clean_params, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))


def resolve_tracking_url(url: str, timeout: int = 5) -> str:
    """Resolve a tracking URL to its final destination by following redirects.

    Returns the clean final URL (without UTM params), or the original URL on failure.
    """
    if not is_tracking_url(url):
        return url
    try:
        import requests
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
        final_url = resp.url
        return strip_utm_params(final_url)
    except Exception as e:
        logger.warning(f"Could not resolve tracking URL: {url} — {e}")
        return url


def resolve_tracking_urls_in_html(html_content: str) -> str:
    """Find all tracking URLs in <a href="..."> tags and resolve them before text conversion."""
    urls_to_resolve = {}

    def collect_url(match):
        url = match.group(1)
        if is_tracking_url(url) and url not in urls_to_resolve:
            urls_to_resolve[url] = None  # placeholder
        return match.group(0)

    re.sub(r'<a\s+[^>]*href="([^"]*)"', collect_url, html_content, flags=re.IGNORECASE)

    if not urls_to_resolve:
        return html_content

    logger.info(f"Resolving {len(urls_to_resolve)} tracking URL(s)...")
    for url in urls_to_resolve:
        resolved = resolve_tracking_url(url)
        urls_to_resolve[url] = resolved
        if resolved != url:
            logger.info(f"  {url[:60]}... → {resolved[:80]}")

    for original, resolved in urls_to_resolve.items():
        if resolved != original:
            html_content = html_content.replace(original, resolved)

    return html_content


def html_to_text(html_content: str) -> str:
    """Convert HTML email to readable plain text, preserving links."""
    text = html_content
    # Remove <head>, <style>, <script> blocks entirely
    text = re.sub(r"<head\b[^>]*>.*?</head\b[^>]*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style\b[^>]*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<script\b[^>]*>.*?</script\b[^>]*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # <br> -> newline
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Block elements -> newlines
    text = re.sub(r"</?(?:p|div|tr|table|section|article|header|footer)\s*[^>]*>", "\n", text, flags=re.IGNORECASE)
    # <h1-h6> -> newline + ## prefix
    text = re.sub(r"<h([1-6])\s*[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]\s*>", "\n", text, flags=re.IGNORECASE)
    # <li> -> bullet
    text = re.sub(r"<li\s*[^>]*>", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li\s*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[uo]l\s*[^>]*>", "\n", text, flags=re.IGNORECASE)
    # <a href="...">text</a> -> text (URL)
    text = re.sub(r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"\2 (\1)", text, flags=re.IGNORECASE | re.DOTALL)
    # <strong>/<b> -> **text**
    text = re.sub(r"<(?:strong|b)\s*>(.*?)</(?:strong|b)\s*>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    # <em>/<i> -> *text*
    text = re.sub(r"<(?:em|i)\s*>(.*?)</(?:em|i)\s*>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Strip trailing whitespace per line
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    # Collapse excessive blank lines (3+ -> 2)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_sender_name(from_header: str) -> str:
    """Extract display name from 'From' header. 'John Doe <john@example.com>' -> 'John Doe'."""
    match = re.match(r'^"?([^"<]+)"?\s*<', from_header)
    if match:
        return match.group(1).strip()
    return from_header


def main():
    parser = argparse.ArgumentParser(
        description="Import Gmail emails into Lenie AI database."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", help="Gmail message ID to import")
    group.add_argument("--search", help="Gmail search query (e.g. 'subject:AI Flash')")

    parser.add_argument("--list", action="store_true", help="With --search: list matching emails without importing")
    parser.add_argument("--max-results", type=int, default=10, help="Max search results (default: 10)")
    parser.add_argument("--source", default="email", help="Source identifier (default: email)")
    parser.add_argument("--note", help="Note to attach to the document")
    parser.add_argument("--language", help="Language code (e.g. pl, en)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without DB writes")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    t_start = time.time()

    # Search mode
    if args.search:
        messages = search_emails(args.search, args.max_results)
        if not messages:
            print("No emails found matching the query.")
            sys.exit(0)

        if args.list:
            print(f"\nFound {len(messages)} email(s):\n")
            for msg_info in messages:
                msg = get_email(msg_info["id"])
                subject = extract_header(msg, "Subject") or "(no subject)"
                from_header = extract_header(msg, "From") or ""
                date = extract_header(msg, "Date") or ""
                print(f"  ID: {msg_info['id']}")
                print(f"  Subject: {subject}")
                print(f"  From: {from_header}")
                print(f"  Date: {date}")
                print()
            sys.exit(0)

        if len(messages) > 1:
            print(f"Found {len(messages)} emails. Use --list to see them, or --id to import a specific one.")
            sys.exit(1)

        msg_id = messages[0]["id"]
    else:
        msg_id = args.id

    # Fetch email
    logging.info(f"Fetching email {msg_id}...")
    msg = get_email(msg_id)

    subject = extract_header(msg, "Subject") or "(no subject)"
    from_header = extract_header(msg, "From") or ""
    date_header = extract_header(msg, "Date") or ""
    author = extract_sender_name(from_header)

    # Extract body — prefer text/html, fallback to text/plain
    html_body = find_body_part(msg["payload"], "text/html")
    plain_body = find_body_part(msg["payload"], "text/plain")

    if html_body:
        html_body = resolve_tracking_urls_in_html(html_body)
        text = html_to_text(html_body)
        text_raw = html_body
    elif plain_body:
        text = plain_body
        text_raw = plain_body
    else:
        print("Error: could not extract email body.")
        sys.exit(1)

    # Detect language from content (first 500 chars)
    language = args.language
    if not language:
        try:
            from library.text_detect_language import text_language_detect
            language = text_language_detect(text[:500])
            logging.info(f"Detected language: {language}")
        except Exception:
            logging.warning("Could not detect language, leaving empty")

    url = f"gmail://{msg_id}"

    # Print summary
    print(f"\n--- Email Summary ---")
    print(f"  Message ID: {msg_id}")
    print(f"  Subject:    {subject}")
    print(f"  From:       {from_header}")
    print(f"  Author:     {author}")
    print(f"  Date:       {date_header}")
    print(f"  Language:   {language}")
    print(f"  Text length: {len(text)} characters")
    print(f"  Source:     {args.source}")
    print(f"---------------------")

    if args.dry_run:
        print("\n[DRY RUN] Would import this email. Text preview (first 500 chars):\n")
        preview = text[:500].encode("ascii", errors="replace").decode("ascii")
        print(preview)
        sys.exit(0)

    # Import to database
    session = get_session()
    try:
        # Check for duplicates
        existing = WebDocument.get_by_url(session, url)
        if existing:
            print(f"\nEmail already exists in DB with ID: {existing.id}")
            sys.exit(0)

        doc = WebDocument(url=url)
        doc.document_type = StalkerDocumentType.email.name
        doc.title = subject
        doc.author = author
        doc.text = text
        doc.text_raw = text_raw
        doc.source = args.source
        doc.original_id = msg_id
        doc.document_state = StalkerDocumentStatus.DOCUMENT_INTO_DATABASE.name
        if language:
            doc.language = language
        if args.note:
            doc.note = args.note

        session.add(doc)
        session.commit()

        elapsed = time.time() - t_start
        print(f"\n  Document created with ID: {doc.id}")
        print(f"  Status: {doc.document_state}")
        print(f"  Elapsed: {elapsed:.2f}s")

    except Exception as e:
        session.rollback()
        logging.error(f"Error importing email: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
