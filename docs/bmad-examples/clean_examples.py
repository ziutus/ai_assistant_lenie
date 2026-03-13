#!/usr/bin/env python3
"""
Cleans BMad Method example files by removing Claude Code tool noise
(file diffs, read/search/explore output) and replacing it with short comments.

Usage:
    python clean_examples.py                    # Process all .txt files in this directory
    python clean_examples.py file1.txt file2.txt  # Process specific files

Output files are saved with _clean suffix (e.g. PRD_arch_clean.txt).
"""

import re
import sys
from pathlib import Path


def is_new_block_start(line: str) -> bool:
    """Check if line starts a new logical block (user prompt, tool call, or AI response)."""
    stripped = line.strip()
    if stripped.startswith('❯'):
        return True
    if stripped.startswith('●'):
        return True
    if stripped.startswith('✻'):
        return True
    return False


def is_continuation_line(line: str) -> bool:
    """Check if line is a ⎿ continuation from a tool call."""
    return '⎿' in line


def is_tool_single_line(line: str) -> bool:
    """Check if line is a single-line tool output (Read, Searched, Explore, etc.)."""
    patterns = [
        r'^● Read \d+ files?\s*\(ctrl\+o',
        r'^● Searched for \d+ patterns?',
        r'^● Explore\(',
        r'^● Skill\(',
        r'^● Searched for \d+ patterns?, read \d+ files?',
    ]
    return any(re.match(p, line.strip()) for p in patterns)


def is_tool_block_start(line: str, next_line: str = '') -> bool:
    """Check if line starts a multi-line tool block (Update/Write with diff).
    Handles long paths that wrap to the next line."""
    stripped = line.strip()
    if re.match(r'^● (Update|Write|Edit)\(.+\)$', stripped):
        return True
    # Wrapped case: "● Write(long-path..." on this line, "       ...path)" on next
    if re.match(r'^● (Update|Write|Edit)\(', stripped) and not stripped.endswith(')'):
        combined = stripped + next_line.strip()
        if re.match(r'^● (Update|Write|Edit)\(.+\)$', combined):
            return True
    return False


def is_status_line(line: str) -> bool:
    """Check if line is a status/timing line."""
    stripped = line.strip()
    return stripped.startswith('✻')


def is_banner_line(line: str) -> bool:
    """Check if line is part of the Claude Code startup banner."""
    patterns = [
        r'▐▛███▜▌',
        r'▝▜█████▛▘',
        r'▘▘ ▝▝',
        r'Claude Code v\d+',
        r'Opus \d+\.\d+ · Claude',
        r'Welcome back',
        r'Recent activity',
        r'No recent activity',
        r"What's new",
        r'Added [`/]',
        r'Added cron',
        r'Added `voice',
        r'/release-notes for more',
        r'Organization',
        r'^╭─',
        r'^╰─',
        r'^│',
        r'^├─',
    ]
    stripped = line.strip()
    return any(re.search(p, stripped) for p in patterns)


def extract_tool_name(line: str, next_line: str = '') -> str:
    """Extract the operation and filename from a tool line (handles wrapped paths)."""
    combined = line.strip()
    if not combined.endswith(')') and next_line:
        combined = combined + next_line.strip()
    m = re.match(r'^● (Update|Write|Edit)\((.+)\)$', combined)
    if m:
        op = m.group(1)
        filepath = m.group(2)
        filename = Path(filepath.replace('\\', '/')).name
        return f"{op}: {filename}"
    return ""


def clean_file(input_path: Path) -> Path:
    """Clean a single file and return the output path."""
    lines = input_path.read_text(encoding='utf-8').splitlines()
    output_lines = []
    i = 0
    in_banner = False
    banner_replaced = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Banner box detection
        if is_banner_line(line):
            if not banner_replaced:
                in_banner = True
            if in_banner:
                i += 1
                continue

        if in_banner and stripped == '':
            in_banner = False
            banner_replaced = True
            output_lines.append('')
            i += 1
            continue

        in_banner = False

        # Status/timing lines — remove
        if is_status_line(line):
            i += 1
            continue

        # Single-line tool outputs (Read, Searched, Explore) — remove
        if is_tool_single_line(line):
            # Also skip the ⎿ continuation lines that follow
            i += 1
            while i < len(lines) and is_continuation_line(lines[i]):
                i += 1
            continue

        # Multi-line tool blocks (Update/Write/Edit with diffs)
        next_line = lines[i + 1] if i + 1 < len(lines) else ''
        if is_tool_block_start(line, next_line):
            tool_info = extract_tool_name(line, next_line)
            i += 1
            # Skip the wrapped continuation of the tool line itself
            if not line.strip().endswith(')') and i < len(lines):
                i += 1

            # Consume ALL lines until next block start or empty line followed by non-indented text
            # The diff block consists of: ⎿ summary, then numbered/indented diff lines
            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()

                # Stop at next tool call, user prompt, or AI paragraph
                if is_new_block_start(next_line):
                    break

                # Stop at an empty line ONLY if next non-empty line is a new block
                if next_stripped == '':
                    # Look ahead to see what comes next
                    j = i + 1
                    while j < len(lines) and lines[j].strip() == '':
                        j += 1
                    if j < len(lines) and is_new_block_start(lines[j]):
                        break
                    # If next non-empty line is still diff-like (indented with numbers), keep consuming
                    if j < len(lines) and re.match(r'^\s{4,}\d+\s', lines[j]):
                        i += 1
                        continue
                    # Otherwise this empty line ends the diff block
                    break

                # This is a diff content line — skip it
                i += 1

            output_lines.append(f'  [--- {tool_info} — diff removed for readability ---]')
            output_lines.append('')
            continue

        # ⎿ continuation lines following tool single-liners we already removed
        if is_continuation_line(line):
            # Check context: if this follows a removed tool line, skip it
            # Look at what's in output_lines
            last_output = ''
            for ol in reversed(output_lines):
                if ol.strip():
                    last_output = ol.strip()
                    break
            # If the last output line is a [--- removed ---] comment or empty, skip
            if last_output.startswith('[---'):
                i += 1
                continue
            # Keep other continuation lines (user prompt continuations, error messages)
            output_lines.append(line)
            i += 1
            continue

        # Regular line — keep
        output_lines.append(line)
        i += 1

    # Collapse consecutive identical [--- ... ---] comments into one with count
    collapsed_lines = []
    i2 = 0
    while i2 < len(output_lines):
        line = output_lines[i2]
        m = re.match(r'^\s*\[--- (.+?) — diff removed for readability ---\]$', line)
        if m:
            tool_info = m.group(1)
            count = 1
            j = i2 + 1
            # Look ahead for same comment (possibly separated by blank lines)
            while j < len(output_lines):
                if output_lines[j].strip() == '':
                    j += 1
                    continue
                m2 = re.match(r'^\s*\[--- (.+?) — diff removed for readability ---\]$', output_lines[j])
                if m2 and m2.group(1) == tool_info:
                    count += 1
                    j += 1
                else:
                    break
            if count > 1:
                collapsed_lines.append(f'  [--- {tool_info} — {count} edits, diffs removed for readability ---]')
            else:
                collapsed_lines.append(line)
            collapsed_lines.append('')
            i2 = j
        else:
            collapsed_lines.append(line)
            i2 += 1

    # Clean up excessive blank lines (max 2 consecutive)
    final_lines = []
    blank_count = 0
    for line in collapsed_lines:
        if line.strip() == '':
            blank_count += 1
            if blank_count <= 2:
                final_lines.append(line)
        else:
            blank_count = 0
            final_lines.append(line)

    output_path = input_path.with_stem(input_path.stem + '_clean')
    output_path.write_text('\n'.join(final_lines) + '\n', encoding='utf-8')
    return output_path


def main():
    script_dir = Path(__file__).parent

    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:]]
    else:
        files = sorted(script_dir.glob('*.txt'))
        # Exclude already cleaned files
        files = [f for f in files if not f.stem.endswith('_clean')]

    if not files:
        print("No .txt files found to process.")
        return

    for f in files:
        if not f.exists():
            print(f"  SKIP: {f} not found")
            continue
        output = clean_file(f)
        original_lines = len(f.read_text(encoding='utf-8').splitlines())
        cleaned_lines = len(output.read_text(encoding='utf-8').splitlines())
        reduction = round((1 - cleaned_lines / original_lines) * 100) if original_lines else 0
        print(f"  {f.name} -> {output.name} ({original_lines} -> {cleaned_lines} lines, -{reduction}%)")


if __name__ == '__main__':
    main()
