# Backend Data — CLAUDE.md

Site-specific rules for extracting article content from Polish news portals. These rules strip navigation, ads, social sharing buttons, legal notices, and other non-article elements from downloaded webpage content (converted to Markdown).

## Directory Structure

```
data/
├── site_rules.json        # JSON-based cleanup rules (remove before/after/string)
└── pages_analyze/         # Regex patterns for article text extraction
    ├── money*.regex       # money.pl
    ├── wiadomosci_wp_pl*.regex    # wiadomosci.wp.pl
    ├── tech_wp_pl*.regex          # tech.wp.pl
    ├── onet_pl_*.regex            # onet.pl (various sections)
    ├── wiadomosci_onet_pl*.regex  # wiadomosci.onet.pl
    ├── businessinsider_com_pl*.regex  # businessinsider.com.pl
    ├── interia_pl_*.regex         # wydarzenia.interia.pl, biznes.interia.pl
    ├── geekweek_interia_pl*.regex # geekweek.interia.pl
    └── o2_pl_*.regex              # o2.pl
```

## Two Cleanup Mechanisms

### 1. `site_rules.json` — Simple string/regex removal

Used by `library/website/website_download_context.py` → `webpage_text_clean()` for basic content cleanup during HTML download. Structure per domain:

```json
{
    "https://www.money.pl": {
        "remove_before": ["regex patterns — remove everything before the match"],
        "remove_after": ["regex patterns — remove everything after the match"],
        "remove_string": ["literal strings to remove"],
        "remove_string_regexp": ["regex patterns to remove inline"]
    }
}
```

### 2. `pages_analyze/*.regex` — Full article extraction patterns

Used by `webdocument_md_decode.py` for precise article body extraction from Markdown-converted content. Each `.regex` file contains a **single multiline regex** applied with `re.DOTALL` to match the entire page structure and capture the article text via named group.

Key conventions in `.regex` files:
- **`(?P<article_text>...)`** — named capture group containing the extracted article body (required)
- **`(?P<title>...)`** — optional named capture group for the article title
- Lines before `(?P<article_text>...)` match page header/navigation to skip
- Lines after `(?P<article_text>...)` match page footer/boilerplate to stop extraction
- `.*?` (non-greedy) used between structural markers
- Polish month names matched via alternation: `(?:stycznia|lutego|marca|...)`

Example pattern structure (simplified):
```regex
\[Navigation\]\(/link\)\s+           ← skip navigation
date_pattern\s+                       ← skip date header
(?P<article_text>.*?)                 ← capture article body
Footer\stext\sto\sstop\smatching     ← stop at footer
```

## URL-to-Regex Mapping

The mapping from website URLs to their regex files is defined in `webdocument_md_decode.py` → `page_regexp_map` dictionary. Each URL prefix maps to an ordered list of `.regex` files — they are tried in sequence until one matches.

Supported portals:
| URL prefix | Regex files |
|------------|------------|
| `money.pl` | 9 patterns |
| `wiadomosci.wp.pl` | 4 patterns |
| `tech.wp.pl` | 5 patterns (shares some with wp.pl) |
| `onet.pl` (multiple sections) | ~20 patterns across informacje, wiadomosci, podroze, motoryzacja, premium |
| `businessinsider.com.pl` | 2 patterns |
| `interia.pl` (wydarzenia, biznes) | 7 patterns |
| `geekweek.interia.pl` | 3 patterns |
| `o2.pl` | 3 patterns |

## File Naming Convention

- **`{domain}_{id}.regex`** — rule for a specific document ID (e.g., `interia_pl_7456.regex` was created/tested against document #7456)
- **`{domain}_{year}_{variant}.regex`** — rule created for a specific year's page layout (e.g., `money_2025_1.regex`)
- **`{domain}.regex`** / **`{domain}{N}.regex`** — general/legacy rules (e.g., `money.regex`, `money2.regex`)

## Adding New Rules

1. Download the target page and convert to Markdown (the system uses `markitdown`, `html2text`, or `html2markdown`)
2. Identify the structural markers (navigation, date, sharing buttons, footer) surrounding the article text
3. Write a regex with `(?P<article_text>...)` capturing only the article body
4. Save as `pages_analyze/{domain_underscored}_{id_or_year_variant}.regex`
5. Add the file path to `page_regexp_map` in `webdocument_md_decode.py` under the appropriate URL prefix
6. For simple before/after removal rules, add entries to `site_rules.json` instead
