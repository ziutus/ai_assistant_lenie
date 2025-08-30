import json
import re


def time_to_seconds(time_str: str) -> int:
    if time_str.count(':') == 2:
        hours, minutes, seconds = map(int, time_str.split(':'))
        return (hours * 3600) + (minutes * 60 + seconds)
    else:
        minutes, seconds = map(int, time_str.split(':'))
        return minutes * 60 + seconds


def split_text_and_time(input_string: str | None) -> dict[str, str] | None:
    if input_string is None:
        return None

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
        return None


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


def text_split_with_chapters(transcript_string: str | None, chapters_string: str | None = None) -> str | None:
    if transcript_string is None:
        return None
    if chapters_string is None:
        return transcript_string

    chapters = chapters_text_to_list(chapters_string)

    json_data = json.loads(transcript_string)

    chapter_nb = 0
    string_all = chapters[chapter_nb]['title'] + "\n"
    for transcript in json_data['results']["items"]:

        if 'start_time' in transcript:
            chapter_start = time_to_seconds(chapters[chapter_nb]['start'])
            chapter_end = time_to_seconds(chapters[chapter_nb]['end'])
            transcript_start_time = float(transcript['start_time'])

            if chapter_start <= transcript_start_time <= chapter_end:
                string_all += " " + transcript['alternatives'][0]['content']
            else:
                chapter_nb += 1
                string_all += "\n\n" + chapters[chapter_nb]['title'] + "\n" + transcript['alternatives'][0]['content']
        else:
            string_all += transcript['alternatives'][0]['content']

    return string_all


def youtube_titles_to_text(titles_text: str | None = None) -> str | None:
    transcript = json.loads(titles_text)
    string_all = ""
    for entry in transcript:
        string_all += entry['text'] + "\n"

    return string_all


def youtube_titles_split_with_chapters(titles_text: str | None = None, chapter_list_text: str | None = None) -> str | None:
    transcript = json.loads(titles_text)
    chapters = chapters_text_to_list(chapter_list_text)

    chapter_nb = 0
    string_all = chapters[chapter_nb]['title'] + "\n"
    for entry in transcript:

        if 'start' in entry:
            chapter_start = time_to_seconds(chapters[chapter_nb]['start'])
            chapter_end = time_to_seconds(chapters[chapter_nb]['end'])
            entry_start_time = float(entry['start'])

            if chapter_start <= entry_start_time <= chapter_end:
                string_all += " " + entry['text']
            else:
                chapter_nb += 1
                string_all += "\n\n" + chapters[chapter_nb]['title'] + "\n" + \
                              entry['text']
        else:
            string_all += entry['text']

    return string_all
