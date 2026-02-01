#!/usr/bin/env python3
"""
Script to sync Google Calendar events to Obsidian daily journal files.

Prerequisites:
1. Enable Google Calendar API in Google Cloud Console
2. Create OAuth 2.0 credentials (Desktop application)
3. Download credentials.json and place in this directory
4. Install required packages:
   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Usage:
    python google_calendar_to_obsidian.py                    # Today's events
    python google_calendar_to_obsidian.py 2025-01-29         # Specific date
    python google_calendar_to_obsidian.py 2025-01-29 --auto  # Auto-approve (no confirmation)
"""
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
JOURNAL_DIR = Path(r"C:\Users\ziutus\Obsydian\personal\Journal")
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.json"
TIMEZONE = "Europe/Warsaw"

# Section header for calendar events in journal
CALENDAR_SECTION_HEADER = "## Kalendarz"

# Events to ignore (case-insensitive substring matching)
IGNORED_EVENTS = [
    "wziąć leki",
    "wziąć Milurit"
]


def get_calendar_service():
    """
    Authenticate and return Google Calendar service.
    On first run, opens browser for OAuth consent.
    """
    creds = None

    # Load existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"Error: Credentials file not found: {CREDENTIALS_FILE}")
                print("\nTo set up Google Calendar API:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project or select existing one")
                print("3. Enable 'Google Calendar API'")
                print("4. Create OAuth 2.0 credentials (Desktop application)")
                print(f"5. Download and save as: {CREDENTIALS_FILE}")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        TOKEN_FILE.write_text(creds.to_json())
        print(f"Token saved to: {TOKEN_FILE}")

    return build("calendar", "v3", credentials=creds)


def get_events_for_date(service, target_date: datetime) -> list[dict]:
    """
    Fetch all events for a specific date from all calendars.

    Args:
        service: Google Calendar API service
        target_date: Date to fetch events for

    Returns:
        List of event dictionaries sorted by start time
    """
    tz = ZoneInfo(TIMEZONE)

    # Set time range for the entire day
    start_of_day = datetime(
        target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz
    )
    end_of_day = start_of_day + timedelta(days=1)

    # Convert to RFC3339 format
    time_min = start_of_day.isoformat()
    time_max = end_of_day.isoformat()

    all_events = []

    try:
        # Get list of all calendars
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get("items", [])

        for calendar in calendars:
            calendar_id = calendar["id"]
            calendar_name = calendar.get("summary", "Unknown")

            try:
                events_result = (
                    service.events()
                    .list(
                        calendarId=calendar_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )

                events = events_result.get("items", [])

                for event in events:
                    event["_calendar_name"] = calendar_name
                    all_events.append(event)

            except HttpError as e:
                if e.resp.status == 404:
                    # Calendar not accessible
                    continue
                raise

    except HttpError as error:
        print(f"Error fetching events: {error}")
        return []

    # Sort by start time
    def get_start_time(event):
        start = event.get("start", {})
        if "dateTime" in start:
            return start["dateTime"]
        return start.get("date", "")

    all_events.sort(key=get_start_time)

    return all_events


def format_event_time(event: dict) -> str:
    """
    Format event time for display.

    Returns:
        Formatted time string (e.g., "09:00-10:30" or "Cały dzień")
    """
    start = event.get("start", {})
    end = event.get("end", {})

    # All-day event
    if "date" in start:
        return "Cały dzień"

    # Timed event
    start_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00"))

    # Convert to local timezone
    tz = ZoneInfo(TIMEZONE)
    start_local = start_dt.astimezone(tz)
    end_local = end_dt.astimezone(tz)

    return f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}"


def should_ignore_event(event: dict) -> bool:
    """
    Check if event should be ignored based on IGNORED_EVENTS list.

    Args:
        event: Event dictionary

    Returns:
        True if event should be ignored, False otherwise
    """
    summary = event.get("summary", "").lower()
    return any(ignored.lower() in summary for ignored in IGNORED_EVENTS)


def format_events_as_markdown(events: list[dict], target_date: datetime) -> str:
    """
    Format events as markdown for Obsidian journal.

    Args:
        events: List of event dictionaries
        target_date: The date for context

    Returns:
        Formatted markdown string
    """
    # Filter out ignored events
    filtered_events = [e for e in events if not should_ignore_event(e)]

    if not filtered_events:
        return f"{CALENDAR_SECTION_HEADER}\n_Brak wydarzeń_\n"

    lines = [CALENDAR_SECTION_HEADER]

    for event in filtered_events:
        summary = event.get("summary", "Bez tytułu")
        time_str = format_event_time(event)
        location = event.get("location", "")
        description = event.get("description", "")
        calendar_name = event.get("_calendar_name", "")

        # Main event line
        if time_str == "Cały dzień":
            lines.append(f"- **{summary}** (cały dzień)")
        else:
            lines.append(f"- **{time_str}** - {summary}")

        # Optional details as sub-items
        if location:
            lines.append(f"  - 📍 {location}")

        if calendar_name and calendar_name not in ["Primary", summary]:
            lines.append(f"  - 📅 {calendar_name}")

        # Add short description if present (first line only)
        if description:
            first_line = description.split("\n")[0].strip()
            if first_line and len(first_line) < 200:
                lines.append(f"  - {first_line}")

    lines.append("")  # Empty line at end
    return "\n".join(lines)


def get_journal_file_path(target_date: datetime) -> Path:
    """
    Get the path to the journal file for a specific date.

    Args:
        target_date: Date for the journal file

    Returns:
        Path to the journal file
    """
    weekday = target_date.strftime("%a")  # Mon, Tue, etc.
    filename = f"{target_date.strftime('%Y-%m-%d')}-{weekday}.md"
    return JOURNAL_DIR / filename


def read_journal_file(file_path: Path) -> str:
    """Read journal file content or return empty string if not exists."""
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return ""


def update_journal_with_events(file_path: Path, events_markdown: str) -> str:
    """
    Update or create journal file with calendar events section.

    If calendar section exists, it will be replaced.
    If not, it will be added at the beginning.

    Args:
        file_path: Path to the journal file
        events_markdown: Formatted markdown for events

    Returns:
        New content of the journal file
    """
    content = read_journal_file(file_path)

    # Check if calendar section already exists
    if CALENDAR_SECTION_HEADER in content:
        # Find the section and replace it
        lines = content.split("\n")
        new_lines = []
        in_calendar_section = False
        section_replaced = False

        for line in lines:
            if line.strip() == CALENDAR_SECTION_HEADER.strip():
                in_calendar_section = True
                if not section_replaced:
                    new_lines.append(events_markdown.rstrip())
                    section_replaced = True
                continue

            if in_calendar_section:
                # End of calendar section when we hit another ## header or end
                if line.startswith("## ") or line.startswith("# "):
                    in_calendar_section = False
                    new_lines.append(line)
                # Skip lines in calendar section
                continue

            new_lines.append(line)

        return "\n".join(new_lines)

    else:
        # Add calendar section at the beginning (after first # header if exists)
        lines = content.split("\n")

        if lines and lines[0].startswith("# "):
            # Insert after the main header
            return lines[0] + "\n" + events_markdown + "\n" + "\n".join(lines[1:])
        else:
            # Insert at the beginning
            return events_markdown + "\n" + content


def main():
    parser = argparse.ArgumentParser(
        description="Sync Google Calendar events to Obsidian journal"
    )
    parser.add_argument(
        "date",
        nargs="?",
        default=None,
        help="Date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--auto",
        "-a",
        action="store_true",
        help="Auto-approve without confirmation",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be written without modifying files",
    )

    args = parser.parse_args()

    # Parse target date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        target_date = datetime.now()

    print(f"Fetching events for: {target_date.strftime('%Y-%m-%d (%A)')}")
    print("-" * 50)

    # Get calendar service
    service = get_calendar_service()

    # Fetch events
    events = get_events_for_date(service, target_date)
    ignored_count = sum(1 for e in events if should_ignore_event(e))
    print(f"Found {len(events)} event(s) ({ignored_count} ignored)")

    # Format as markdown
    events_markdown = format_events_as_markdown(events, target_date)

    # Show preview
    print("\n--- Preview ---")
    print(events_markdown)
    print("--- End Preview ---\n")

    # Get journal file path
    journal_file = get_journal_file_path(target_date)
    print(f"Journal file: {journal_file}")

    if journal_file.exists():
        print("File exists - calendar section will be updated/added")
    else:
        print("File does not exist - will be created")

    # Generate new content
    new_content = update_journal_with_events(journal_file, events_markdown)

    if args.dry_run:
        print("\n[DRY RUN] Would write:")
        print("=" * 50)
        print(new_content)
        print("=" * 50)
        return

    # Ask for confirmation
    if not args.auto:
        response = input("\nDo you want to save? [y/N]: ").strip().lower()
        if response not in ("y", "yes", "t", "tak"):
            print("Cancelled.")
            return

    # Write to file
    journal_file.parent.mkdir(parents=True, exist_ok=True)
    journal_file.write_text(new_content, encoding="utf-8")
    print(f"\nSaved to: {journal_file}")


if __name__ == "__main__":
    main()
