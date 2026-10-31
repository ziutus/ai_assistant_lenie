"""Fetch a public Luma profile and print its fields as JSON.

Usage: python -I luma_profile.py <luma profile URL> [--photo <output path>]

Needs no login and no browser: the public profile page embeds the profile in
its server-rendered __NEXT_DATA__ block. Only luma.com / lu.ma hosts are fetched.
"""

import argparse
import json
import re
import sys
import urllib.request
from urllib.parse import urlparse

ALLOWED_HOSTS = {"luma.com", "www.luma.com", "lu.ma", "www.lu.ma"}
AVATAR_HOSTS = {"images.lumacdn.com"}
USER_AGENT = "Mozilla/5.0"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - host checked by caller
        return response.read()


def fetch_profile(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"not a Luma profile URL: {url}")
    html = _get(url).decode("utf-8")
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("no __NEXT_DATA__ block - Luma page layout changed or page is not a profile")
    user = json.loads(match.group(1))["props"]["pageProps"]["initialData"]["user"]
    linkedin = user.get("linkedin_handle")
    return {
        "luma_id": user.get("api_id"),
        "name": user.get("name"),
        "bio_short": user.get("bio_short"),
        "avatar_url": user.get("avatar_url"),
        # Luma serves a stock picture (cdn.lu.ma/avatars-default/...) when the person set none.
        "avatar_is_default": "avatars-default" in (user.get("avatar_url") or ""),
        "timezone": user.get("timezone"),
        "website": user.get("website"),
        "linkedin_url": f"https://www.linkedin.com{linkedin}" if linkedin else None,
        "twitter_handle": user.get("twitter_handle"),
        "instagram_handle": user.get("instagram_handle"),
        "youtube_handle": user.get("youtube_handle"),
        "tiktok_handle": user.get("tiktok_handle"),
        # Luma stores a separate first/last name that can differ from the display name
        # (seen: display "Marti Kuc", stored "Kama Mare") - never use them as identity.
        "stored_first_name": user.get("first_name"),
        "stored_last_name": user.get("last_name"),
    }


def download_photo(avatar_url: str, path: str) -> None:
    parsed = urlparse(avatar_url)
    if parsed.scheme != "https" or parsed.hostname not in AVATAR_HOSTS:
        raise ValueError(f"unexpected avatar host: {avatar_url}")
    with open(path, "wb") as handle:
        handle.write(_get(avatar_url))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--photo", help="download the avatar to this path")
    args = parser.parse_args()
    profile = fetch_profile(args.url)
    if args.photo and profile["avatar_url"] and not profile["avatar_is_default"]:
        download_photo(profile["avatar_url"], args.photo)
        profile["photo_path"] = args.photo
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
