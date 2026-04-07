#!/usr/bin/env python3
"""Fetch LinkedIn profile data via Apify actor.

Usage:
    cd backend
    python test_code/linkedin_profile.py https://www.linkedin.com/in/krzysztof-jozwiak-sre/
    python test_code/linkedin_profile.py --output json https://www.linkedin.com/in/krzysztof-jozwiak-sre/
"""

import argparse
import json
import sys

from apify_client import ApifyClient

from library.config_loader import load_config

ACTOR_ID = "2SyF0bVxmgGr8IVCZ"

cfg = load_config()


def fetch_linkedin_profiles(profile_urls: list[str]) -> list[dict]:
    """Fetch LinkedIn profile data via Apify."""
    token = cfg.require("APIFY_API_TOKEN")
    client = ApifyClient(token)

    run_input = {"profileUrls": profile_urls}

    print(f"Running Apify actor {ACTOR_ID} for {len(profile_urls)} profile(s)...")
    run = client.actor(ACTOR_ID).call(run_input=run_input)

    results = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        results.append(item)

    return results


def print_profile_summary(profile: dict):
    """Print a human-readable profile summary."""
    print(f"\n{'=' * 60}")
    print(f"Name: {profile.get('firstName', '')} {profile.get('lastName', '')}")
    print(f"Headline: {profile.get('headline', '(none)')}")
    print(f"Location: {profile.get('location', '(none)')}")
    print(f"URL: {profile.get('url', '(none)')}")

    summary = profile.get("summary")
    if summary:
        print(f"\nSummary:\n  {summary[:300]}")

    positions = profile.get("positions", [])
    if positions:
        print(f"\nExperience ({len(positions)} positions):")
        for pos in positions[:5]:
            company = pos.get("companyName", "?")
            title = pos.get("title", "?")
            start = pos.get("startDate", "?")
            end = pos.get("endDate", "present")
            print(f"  - {title} @ {company} ({start} – {end})")

    education = profile.get("education", [])
    if education:
        print(f"\nEducation ({len(education)}):")
        for edu in education[:3]:
            school = edu.get("schoolName", "?")
            degree = edu.get("degreeName", "")
            field = edu.get("fieldOfStudy", "")
            print(f"  - {school}: {degree} {field}".rstrip())

    skills = profile.get("skills", [])
    if skills:
        skill_names = [s.get("name", s) if isinstance(s, dict) else s for s in skills[:15]]
        print(f"\nSkills: {', '.join(skill_names)}")

    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Fetch LinkedIn profile data via Apify")
    parser.add_argument("urls", nargs="+", help="LinkedIn profile URL(s)")
    parser.add_argument("--output", choices=["summary", "json"], default="summary",
                        help="Output format (default: summary)")
    parser.add_argument("--save", metavar="FILE", help="Save raw JSON to file")
    args = parser.parse_args()

    results = fetch_linkedin_profiles(args.urls)

    if not results:
        print("No results returned.")
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for profile in results:
            print_profile_summary(profile)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to {args.save}")


if __name__ == "__main__":
    main()
