#!/usr/bin/env python3
"""Import curated links from unknow.news into PostgreSQL.

DEPRECATED: This script is now a thin wrapper around feed_monitor.py.
The unknow.news feed is configured in feeds.yaml as a json_api feed type.

Usage (unchanged):
    cd backend
    python imports/unknown_news_import.py
    python imports/unknown_news_import.py --since 2026-02-01
    python imports/unknown_news_import.py --since 2026-02-01 --dry-run
    python imports/unknown_news_import.py --since 2026-02-01 --dry-run --limit 5

Equivalent feed_monitor.py commands:
    python imports/feed_monitor.py --import --source "unknow.news"
    python imports/feed_monitor.py --import --source "unknow.news" --since 2026-02-01
    python imports/feed_monitor.py --import --source "unknow.news" --dry-run
"""

import sys

print("=" * 60)
print("DEPRECATED: use feed_monitor.py instead:")
print('  python imports/feed_monitor.py --import --source "unknow.news"')
print("=" * 60)
print()

# Build equivalent feed_monitor.py arguments
args = ["--import", "--source", "unknow.news"]

i = 1
while i < len(sys.argv):
    arg = sys.argv[i]
    if arg == "--since" and i + 1 < len(sys.argv):
        args.extend(["--since", sys.argv[i + 1]])
        i += 2
    elif arg == "--dry-run":
        args.append("--dry-run")
        i += 1
    elif arg == "--limit" and i + 1 < len(sys.argv):
        args.extend(["--limit", sys.argv[i + 1]])
        i += 2
    else:
        i += 1

# Replace sys.argv and run feed_monitor
sys.argv = ["feed_monitor.py"] + args
from imports.feed_monitor import main  # noqa: E402
main()
