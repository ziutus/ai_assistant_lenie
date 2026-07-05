import hashlib
import re


def get_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def remove_last_occurrence_and_after(text: str, regex: str) -> str:
    matches = [m for m in re.finditer(regex, text)]
    if matches:
        last_match = matches[-1]
        return text[:last_match.start()]
    else:
        return text


def remove_before_regex(text: str, regex: str) -> str:
    match = re.search(regex, text)
    if match:
        # zwróć wszystko po dopasowanym wzorcu
        return text[match.end():].strip()
    else:
        return text


def remove_after_regex(text: str, regex: str) -> str:
    match = re.search(regex, text)
    if match:
        return text[:match.end()].strip()
    else:
        return text


def remove_text_regex(text: str, regex: str) -> str:
    return re.sub(regex, "", text)


def remove_matching_lines(input_text):
    # Wyrażenie regularne dopasowujące podany format
    pattern = r'^\*\s\[\*\*.*\*\*\]\(https?://[^\)]+\)$'
    # Filtruj linie, które nie pasują do wzorca
    cleaned_lines = [line for line in input_text.splitlines() if not re.match(pattern, line)]
    # Połącz linie z powrotem w tekst
    return '\n'.join(cleaned_lines)


_SENT_BOUNDARY = re.compile(r'(?<=[.!?…])\s+')

# A trailing chunk smaller than this fraction of max_chars gets merged into the
# previous one (accepting a slight overflow) — avoids orphan tails like a
# 320-char chunk when a 5,106-char document meets a 5,000-char limit.
_TAIL_MERGE_RATIO = 0.15


def _merge_small_tail(chunks: list[str], max_chars: int, separator: str) -> list[str]:
    if len(chunks) >= 2 and len(chunks[-1]) < max_chars * _TAIL_MERGE_RATIO:
        tail = chunks.pop()
        chunks[-1] = f"{chunks[-1]}{separator}{tail}"
    return chunks


def split_text_into_sentence_chunks(text: str, max_chars: int) -> list[str]:
    """Split text at sentence boundaries, accumulating up to max_chars per chunk.

    Designed for YouTube transcripts where \\n appears every few words (not at sentence ends).
    First flattens single newlines to spaces so sentences are not broken by line wrapping,
    then splits on sentence-ending punctuation.

    Falls back to mid-sentence split only when a single sentence exceeds max_chars.
    """
    flat = re.sub(r'\n(?!\n)', ' ', text)
    flat = re.sub(r' {2,}', ' ', flat)

    sentences = [s.strip() for s in _SENT_BOUNDARY.split(flat) if s.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for sent in sentences:
        if len(sent) > max_chars:
            if current:
                chunks.append(' '.join(current))
                current = []
                current_size = 0
            for i in range(0, len(sent), max_chars):
                chunks.append(sent[i:i + max_chars])
        elif current_size + len(sent) + 1 > max_chars and current:
            chunks.append(' '.join(current))
            current = [sent]
            current_size = len(sent)
        else:
            current.append(sent)
            current_size += len(sent) + 1

    if current:
        chunks.append(' '.join(current))

    return _merge_small_tail(chunks, max_chars, ' ')


def split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text at double-newline boundaries, respecting max_chars per chunk.

    Falls back to single-newline splitting when a single paragraph exceeds max_chars.
    Suitable for both LLM batch analysis (large chunks) and any other chunking need.
    """
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks: list[str] = []
    current_parts: list[str] = []
    current_size = 0

    for para in paragraphs:
        if len(para) > max_chars:
            if current_parts:
                chunks.append('\n\n'.join(current_parts))
                current_parts = []
                current_size = 0
            line_parts: list[str] = []
            line_size = 0
            for line in [ln.strip() for ln in para.split('\n') if ln.strip()]:
                if line_size + len(line) + 1 > max_chars and line_parts:
                    chunks.append('\n'.join(line_parts))
                    line_parts = [line]
                    line_size = len(line)
                else:
                    line_parts.append(line)
                    line_size += len(line) + 1
            if line_parts:
                chunks.append('\n'.join(line_parts))
        elif current_size + len(para) + 2 > max_chars and current_parts:
            chunks.append('\n\n'.join(current_parts))
            current_parts = [para]
            current_size = len(para)
        else:
            current_parts.append(para)
            current_size += len(para) + 2

    if current_parts:
        chunks.append('\n\n'.join(current_parts))

    return _merge_small_tail(chunks, max_chars, '\n\n')


_MD_HEADER_RE = re.compile(r'^#{1,6} ', re.MULTILINE)


def split_markdown_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split markdown text into chunks, preferring section boundaries (headers).

    Strategy:
      1. Cut the text into sections at markdown headers (#..######) — a header
         always starts a new section and stays with the content that follows it.
      2. Pack consecutive sections into chunks of up to max_chars.
      3. A single section larger than max_chars is split at paragraph boundaries
         (falling back to line/sentence splits via split_text_into_chunks).
      4. Text without any headers degrades to plain paragraph splitting.
    """
    text = text.strip()
    if not text:
        return []

    boundaries = [m.start() for m in _MD_HEADER_RE.finditer(text)]
    if not boundaries:
        return split_text_into_chunks(text, max_chars)

    # Preamble before the first header is its own section
    starts = boundaries if boundaries[0] == 0 else [0] + boundaries
    sections = [
        text[start:end].strip()
        for start, end in zip(starts, starts[1:] + [len(text)])
    ]
    sections = [s for s in sections if s]

    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for section in sections:
        if len(section) > max_chars:
            if current:
                chunks.append('\n\n'.join(current))
                current = []
                current_size = 0
            chunks.extend(split_text_into_chunks(section, max_chars))
        elif current_size + len(section) + 2 > max_chars and current:
            chunks.append('\n\n'.join(current))
            current = [section]
            current_size = len(section)
        else:
            current.append(section)
            current_size += len(section) + 2

    if current:
        chunks.append('\n\n'.join(current))

    return _merge_small_tail(chunks, max_chars, '\n\n')


_CHAPTER_HEADER_RE = re.compile(r'^(#{1,2}) (.+)$', re.MULTILINE)


def detect_chapters(text: str) -> list[dict]:
    """Detect a book-like table of contents from markdown H1/H2 headers.

    Chapter level selection: H1 when the text has at least two H1 headers,
    otherwise H2 (OCR output often promotes everything to one level). A single
    header of either level still yields one chapter. Text before the first
    chapter header (title page, TOC) becomes a "(wstęp)" pseudo-chapter.

    Returns a list of dicts ordered by position in the text:
        {position (1-based), level, title, char_start, char_end, length}
    Empty list when the text has no H1/H2 headers.
    """
    text = text.rstrip()
    if not text:
        return []

    headers = [
        (len(m.group(1)), m.group(2).strip().rstrip('#').strip(), m.start())
        for m in _CHAPTER_HEADER_RE.finditer(text)
    ]
    if not headers:
        return []

    h1_count = sum(1 for level, _, _ in headers if level == 1)
    chapter_level = 1 if h1_count >= 2 or h1_count == len(headers) else 2
    chosen = [(title, start) for level, title, start in headers if level == chapter_level]
    if not chosen:
        return []

    chapters: list[dict] = []
    if chosen[0][1] > 0 and text[:chosen[0][1]].strip():
        chapters.append({"title": "(wstęp)", "char_start": 0, "char_end": chosen[0][1]})
    starts = [start for _, start in chosen]
    for (title, start), end in zip(chosen, starts[1:] + [len(text)]):
        chapters.append({"title": title, "char_start": start, "char_end": end})

    for i, ch in enumerate(chapters, 1):
        ch["position"] = i
        ch["level"] = chapter_level
        ch["length"] = ch["char_end"] - ch["char_start"]
    return chapters


def split_text_for_embedding(text, paragraph_titles=[], max_words_in_line=300, max_characters_in_line=1000):
    sentences2 = []
    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        text_tmp = ""
        for line in paragraph.splitlines():
            if line in paragraph_titles:
                text_tmp += line + "\n"
            else:
                text_tmp += line + " "
        paragraph = text_tmp

        if len(paragraph) < max_characters_in_line:
            text = ""
            for line in paragraph.splitlines():
                if line in paragraph_titles:
                    text += line + "\n"
                else:
                    text += line
            if len(text) > 0:
                sentences2.append(text)
            continue

        sentences = paragraph.split(".")

        for sentence in sentences:
            sentence = sentence.strip()
            while len(sentence) > 0:
                words = sentence.split(" ")
                if len(words) <= max_words_in_line:
                    sentences2.append(sentence)
                    sentence = ""
                    continue

                word_nb = 1
                word_upper_nb = 1
                for word in words:
                    if len(word) > 0:
                        if word[0].isupper():
                            if word_nb > max_words_in_line:
                                break
                            word_upper_nb = word_nb
                    word_nb += 1

                new_string = " ".join(words[:word_upper_nb - 1])
                if len(new_string) > 0:
                    new_string2 = new_string.strip()
                    sentences2.append(new_string2)

                sentence = sentence.replace(new_string, "")
                sentence = sentence.strip()

    return '\n\n'.join(sentences2)
