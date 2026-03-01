#!/usr/bin/env python3
"""CLI test client for Lenie backend API and Slack bot.

Tests the same endpoints that Slack bot slash commands use,
without requiring a full Slack Socket Mode connection.

Usage:
    python client.py version
    python client.py count
    python client.py add https://example.com
    python client.py check https://example.com
    python client.py info 42
    python client.py slack-test
    python client.py interactive

Environment variables:
    LENIE_API_URL   - Backend API URL (default: http://localhost:5000)
    STALKER_API_KEY - API key for backend authentication
    SLACK_BOT_TOKEN - Bot User OAuth Token (only for slack-test command)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

DEFAULT_API_URL = "http://localhost:5000"
HTTP_TIMEOUT = 10


# --- Colors for terminal output ---

class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{Color.GREEN}OK{Color.RESET} {msg}")


def fail(msg: str) -> None:
    print(f"{Color.RED}FAIL{Color.RESET} {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"{Color.CYAN}>{Color.RESET} {msg}")


def header(msg: str) -> None:
    print(f"\n{Color.BOLD}{msg}{Color.RESET}")


# --- API helpers ---


def api_request(method: str, base_url: str, path: str, api_key: str, **kwargs) -> dict:
    """Make an HTTP request to the backend API and return parsed JSON."""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    try:
        resp = requests.request(method, url, headers=headers, timeout=HTTP_TIMEOUT, **kwargs)
    except requests.ConnectionError:
        fail(f"Cannot connect to backend at {base_url}")
        fail("Is the server running? Check LENIE_API_URL.")
        sys.exit(1)
    except requests.Timeout:
        fail(f"Request timed out ({HTTP_TIMEOUT}s): {path}")
        sys.exit(1)

    if resp.status_code >= 400:
        fail(f"HTTP {resp.status_code} for {method} {path}")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text[:500])
        return {}

    try:
        return resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        fail(f"Non-JSON response for {path}")
        print(resp.text[:500])
        return {}


# --- Commands ---


def cmd_version(base_url: str, api_key: str, **_kwargs) -> None:
    """Simulate /lenie-version — show backend version and build info."""
    header("GET /version")
    data = api_request("GET", base_url, "/version", api_key)
    if not data:
        return
    ok(f"Version: {data.get('app_version', '?')}")
    info(f"Build:   {data.get('app_build_time', '?')}")
    info(f"Status:  {data.get('status', '?')}")


def cmd_count(base_url: str, api_key: str, **_kwargs) -> None:
    """Simulate /lenie-count — show document count breakdown."""
    header("GET /website_list (count)")
    doc_types = ("ALL", "webpage", "youtube", "link", "movie", "text_message", "text")

    for doc_type in doc_types:
        data = api_request("GET", base_url, "/website_list", api_key, params={"type": doc_type})
        if not data:
            return
        count = data.get("all_results_count", "?")
        if doc_type == "ALL":
            ok(f"Total documents: {count}")
        elif isinstance(count, int) and count > 0:
            info(f"  {doc_type}: {count}")


def cmd_add(base_url: str, api_key: str, url: str, **_kwargs) -> None:
    """Simulate /lenie-add — add a URL to the knowledge base."""
    header(f"POST /url_add ({url})")
    data = api_request("POST", base_url, "/url_add", api_key, json={"url": url, "type": "link"})
    if not data:
        return
    doc_id = data.get("document_id", "?")
    ok(f"Added to knowledge base (ID: {doc_id}). Type: link.")


def cmd_check(base_url: str, api_key: str, url: str, **_kwargs) -> None:
    """Simulate /lenie-check — check if a URL exists."""
    header(f"GET /website_list (search: {url})")
    data = api_request("GET", base_url, "/website_list", api_key, params={"search_in_document": url})
    if not data:
        return
    websites = data.get("websites", [])
    if websites:
        doc = websites[0]
        ok(f"Found in database (ID: {doc.get('id', '?')})")
        info(f"  Type:    {doc.get('document_type', '?')}")
        info(f"  Status:  {doc.get('document_state', '?')}")
        info(f"  Added:   {doc.get('created_at', '?')}")
    else:
        info("Not found in database.")


def cmd_info(base_url: str, api_key: str, document_id: int, **_kwargs) -> None:
    """Simulate /lenie-info — get document details by ID."""
    header(f"GET /website_get (id={document_id})")
    data = api_request("GET", base_url, "/website_get", api_key, params={"id": document_id})
    if not data:
        return
    ok(f"Document #{document_id}")
    info(f"  Title:   {data.get('title', '?')}")
    info(f"  Type:    {data.get('document_type', '?')}")
    info(f"  Status:  {data.get('document_state', '?')}")
    info(f"  Added:   {data.get('created_at', '?')}")
    url_val = data.get("url", "")
    if url_val:
        info(f"  URL:     {url_val}")


def cmd_health(base_url: str, api_key: str, **_kwargs) -> None:
    """Check all health endpoints."""
    header("Health checks")
    endpoints = ["/", "/healthz", "/startup", "/readiness", "/liveness"]
    for ep in endpoints:
        try:
            resp = requests.get(f"{base_url.rstrip('/')}{ep}", timeout=HTTP_TIMEOUT)
            if resp.status_code < 400:
                ok(f"{ep} -> {resp.status_code}")
            else:
                fail(f"{ep} -> {resp.status_code}")
        except requests.ConnectionError:
            fail(f"{ep} -> connection refused")
        except requests.Timeout:
            fail(f"{ep} -> timeout")


def cmd_slack_test(base_url: str, api_key: str, **_kwargs) -> None:
    """Test Slack bot token connectivity."""
    header("Slack connectivity test")
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        fail("SLACK_BOT_TOKEN not set. Set it in environment to test Slack connectivity.")
        return

    info(f"Token prefix: {token[:10]}...")

    # Test auth
    try:
        resp = requests.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"},
            timeout=HTTP_TIMEOUT,
        )
        data = resp.json()
        if data.get("ok"):
            ok(f"Bot authenticated as: {data.get('user', '?')} in team: {data.get('team', '?')}")
            info(f"  User ID: {data.get('user_id', '?')}")
            info(f"  Team ID: {data.get('team_id', '?')}")
            info(f"  URL:     {data.get('url', '?')}")
        else:
            fail(f"Auth failed: {data.get('error', 'unknown error')}")
            return
    except requests.RequestException as exc:
        fail(f"Cannot reach Slack API: {exc}")
        return

    # Test backend connectivity (from here, not from Slack)
    header("Backend API test (from this machine)")
    cmd_version(base_url, api_key)


def cmd_interactive(base_url: str, api_key: str, **_kwargs) -> None:
    """Interactive mode — type commands like in Slack."""
    header("Interactive mode (type 'help' for commands, 'quit' to exit)")
    print(f"{Color.DIM}Backend: {base_url}{Color.RESET}")
    print()

    while True:
        try:
            raw = input(f"{Color.YELLOW}lenie>{Color.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        command = parts[0].lower().lstrip("/")
        arg = parts[1] if len(parts) > 1 else ""

        if command in ("quit", "exit", "q"):
            print("Bye!")
            break
        elif command in ("help", "h", "?"):
            print("  version          - Show backend version")
            print("  count            - Show document counts")
            print("  add <url>        - Add URL to knowledge base")
            print("  check <url>      - Check if URL exists")
            print("  info <id>        - Get document details")
            print("  health           - Check health endpoints")
            print("  slack-test       - Test Slack token")
            print("  quit             - Exit")
        elif command in ("version", "lenie-version"):
            cmd_version(base_url, api_key)
        elif command in ("count", "lenie-count"):
            cmd_count(base_url, api_key)
        elif command in ("add", "lenie-add"):
            if not arg:
                fail("Usage: add <url>")
            else:
                cmd_add(base_url, api_key, url=arg)
        elif command in ("check", "lenie-check"):
            if not arg:
                fail("Usage: check <url>")
            else:
                cmd_check(base_url, api_key, url=arg)
        elif command in ("info", "lenie-info"):
            try:
                cmd_info(base_url, api_key, document_id=int(arg))
            except ValueError:
                fail("Usage: info <numeric_id>")
        elif command == "health":
            cmd_health(base_url, api_key)
        elif command in ("slack-test", "slack"):
            cmd_slack_test(base_url, api_key)
        else:
            fail(f"Unknown command: {command}. Type 'help' for available commands.")


# --- Main ---


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI test client for Lenie backend API and Slack bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  version       Show backend version and build info (/lenie-version)
  count         Show document count breakdown (/lenie-count)
  add URL       Add a URL to the knowledge base (/lenie-add)
  check URL     Check if a URL exists in the database (/lenie-check)
  info ID       Get document details by ID (/lenie-info)
  health        Check all health endpoints
  slack-test    Test Slack bot token connectivity
  interactive   Interactive mode — type commands like in Slack

Environment variables:
  LENIE_API_URL    Backend API URL (default: http://localhost:5000)
  STALKER_API_KEY  API key for backend authentication
  SLACK_BOT_TOKEN  Bot token (only for slack-test command)
""",
    )
    parser.add_argument(
        "command",
        choices=["version", "count", "add", "check", "info", "health", "slack-test", "interactive"],
        help="Command to execute",
    )
    parser.add_argument("argument", nargs="?", default="", help="Command argument (URL or document ID)")
    parser.add_argument("--url", default=os.environ.get("LENIE_API_URL", DEFAULT_API_URL), help="Backend API URL")
    parser.add_argument("--api-key", default=os.environ.get("STALKER_API_KEY", ""), help="API key for authentication")

    args = parser.parse_args()
    base_url = args.url
    api_key = args.api_key

    if not api_key and args.command not in ("health", "interactive"):
        fail("STALKER_API_KEY not set. Pass --api-key or set the environment variable.")
        sys.exit(1)

    print(f"{Color.DIM}Backend: {base_url}{Color.RESET}")

    cmd_map = {
        "version": cmd_version,
        "count": cmd_count,
        "health": cmd_health,
        "slack-test": cmd_slack_test,
        "interactive": cmd_interactive,
    }

    if args.command in cmd_map:
        cmd_map[args.command](base_url=base_url, api_key=api_key)
    elif args.command == "add":
        if not args.argument:
            fail("Usage: client.py add <url>")
            sys.exit(1)
        cmd_add(base_url=base_url, api_key=api_key, url=args.argument)
    elif args.command == "check":
        if not args.argument:
            fail("Usage: client.py check <url>")
            sys.exit(1)
        cmd_check(base_url=base_url, api_key=api_key, url=args.argument)
    elif args.command == "info":
        if not args.argument:
            fail("Usage: client.py info <document_id>")
            sys.exit(1)
        try:
            doc_id = int(args.argument)
        except ValueError:
            fail("Document ID must be a number")
            sys.exit(1)
        cmd_info(base_url=base_url, api_key=api_key, document_id=doc_id)


if __name__ == "__main__":
    main()
