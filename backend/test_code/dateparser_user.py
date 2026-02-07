import dateparser

dates = [
    "19 stycznia 2026, 21:38",
    "2026-01-20 07:31",
    "Yesterday",
    "2 hours ago",
    "jutro o 15:00"
]

for date_str in dates:
    parsed = dateparser.parse(date_str)
    print(f"Original: '{date_str}' -> Parsed: {parsed}")
