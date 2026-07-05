import bisect
import json
import re


def time_to_seconds(time_str: str) -> int:
    if time_str.count(':') == 2:
        hours, minutes, seconds = map(int, time_str.split(':'))
        return (hours * 3600) + (minutes * 60 + seconds)
    else:
        minutes, seconds = map(int, time_str.split(':'))
        return minutes * 60 + seconds


def split_text_and_time(input_string: str | None) -> dict[str, str]:
    if input_string is None:
        return {}

    match = re.match(r'(.*)\s(\d{1,2}:\d{2})$', input_string)
    if match:
        text, time = match.groups()
        return {'text': text, 'czas': time}
    match2 = re.match(r'^\s*(\d{1,2}:\d{2})\s-?\s?(.*)\s*$', input_string)
    if match2:
        time, text = match2.groups()
        return {'text': text, 'czas': time}
    match3 = re.match(r'^\s*(\d{1,2}:\d{2}:\d{2})\s-?\s?(.*)\s*$', input_string)
    if match3:
        time, text = match3.groups()
        return {'text': text, 'czas': time}
    else:
        return {}


def chapters_text_to_list(chapters_string):
    if chapters_string is None:
        return []

    chapter_list = chapters_string.split('\n')

    chapter_list = [chapter.strip() for chapter in chapter_list if chapter.strip()]
    chapters_simple = []
    chapters = []
    for chapter in chapter_list:
        splitted_data = split_text_and_time(chapter)
        if splitted_data:
            chapters_simple.append(splitted_data)
        else:
            raise Exception("ERROR in creating chapters list")
    del chapter_list

    for i in range(len(chapters_simple)):
        if i < len(chapters_simple) - 1:
            end = chapters_simple[i + 1]['czas']
        else:
            end = '99999:00'
        chapters.append({'start': chapters_simple[i]['czas'], 'end': end, 'title': chapters_simple[i]['text']})
        i += 1
    del chapters_simple
    del i
    del end

    return chapters


def _chapter_index(chapter_starts: list[int], seconds: float, current: int) -> int:
    """Index of the chapter the timestamp falls into (-1 = before the first chapter).

    Never moves backwards — transcripts are processed sequentially and a stray
    out-of-order timestamp must not reopen an earlier chapter.
    """
    return max(bisect.bisect_right(chapter_starts, seconds) - 1, current)


def _append_with_chapters(
    entries: list[dict],
    chapters: list[dict],
    content_key: str,
    start_time_key: str,
) -> str:
    chapter_starts = [time_to_seconds(ch['start']) for ch in chapters]
    chapter_nb = -1  # -1 = intro before the first chapter
    string_all = ""
    after_header = False

    for entry in entries:
        content = entry[content_key]

        if start_time_key in entry:
            target = _chapter_index(chapter_starts, float(entry[start_time_key]), chapter_nb)
            while chapter_nb < target:
                chapter_nb += 1
                string_all += ("\n\n" if string_all else "") + chapters[chapter_nb]['title'] + "\n"
                after_header = True
            if after_header:
                string_all += content
                after_header = False
            elif string_all:
                string_all += " " + content
            else:
                string_all += content
        else:
            # No timestamp (e.g. punctuation) — attach directly, no separator
            string_all += content

    return string_all


def text_split_with_chapters(transcript_string: str | None, chapters_string: str | None = None) -> str | None:
    if transcript_string is None:
        return None
    if chapters_string is None:
        return transcript_string

    chapters = chapters_text_to_list(chapters_string)
    if not chapters:
        return transcript_string

    json_data = json.loads(transcript_string)

    entries = []
    for transcript in json_data['results']["items"]:
        normalized = {'content': transcript['alternatives'][0]['content']}
        if 'start_time' in transcript:
            normalized['start_time'] = transcript['start_time']
        entries.append(normalized)

    return _append_with_chapters(entries, chapters, content_key='content', start_time_key='start_time')


def youtube_titles_to_text(titles_text: str | None = None) -> str | None:
    transcript = json.loads(titles_text)
    string_all = ""
    for entry in transcript:
        string_all += entry['text'] + "\n"

    return string_all


def youtube_titles_split_with_chapters(titles_text: str | None = None, chapter_list_text: str | None = None) -> str | None:
    transcript = json.loads(titles_text)
    chapters = chapters_text_to_list(chapter_list_text)
    if not chapters:
        return youtube_titles_to_text(titles_text)

    entries = []
    for entry in transcript:
        normalized = {'content': entry['text']}
        if 'start' in entry:
            normalized['start_time'] = entry['start']
        entries.append(normalized)

    return _append_with_chapters(entries, chapters, content_key='content', start_time_key='start_time')
