from pprint import pprint

import requests
from bs4 import BeautifulSoup
import re

from library.text_functions import remove_before_regex, remove_last_occurrence_and_after, remove_text_regex
from library.website.website_text_clean_regexp import  remove_before, remove_after, remove_string, remove_string_regexp


def download_raw_html(url: str) -> bytes | None:
    response = requests.get(url)

    if response.status_code == 200:
        return response.content
    else:
        return None


class WebPageParseResult:
    def __init__(self, url: str) -> None:
        self.text_raw = None
        self.text = None
        self.url = url
        self.language : str | None= None
        self.title: str | None = None
        self.summary: str | None = None


def webpage_raw_parse(url: str, raw_html: bytes, analyze_content: bool = True) -> WebPageParseResult:
    soup = BeautifulSoup(raw_html, 'html.parser')
    result = WebPageParseResult(url)
    result.text_raw = soup.get_text()
    result.language = ""

    result.title = soup.title.string if soup.title else ''
    result.summary = soup.find('meta', attrs={'name': 'description'})['content'] if soup.find('meta', attrs={
        'name': 'description'}) else ''

    if soup.find('html'):
        if 'lang' in soup.find('html'):
            result.language = soup.find('html')['lang']

    if analyze_content:
        content = soup.get_text()

        content = re.sub(r'^\n+', '', content)
        content = re.sub(r'\n+$', '', content)
        content = re.sub(r'\n\n+', '\n\n', content)

        for h_size in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            h_elements = soup.find_all(h_size)
            for element in h_elements:
                index = content.find(element.text)
                if index != -1:
                    content = content[:index] + '\n\n' + content[index:]

        bold_elements = soup.find_all('p')
        for element in bold_elements:
            index = content.find(element.text)
            if index != -1:
                content = content[:index] + '\n\n' + content[index:]

        result.text = webpage_text_clean(url, content)

    return result

def webpage_text_clean(url: str, content: str):
    content = re.sub('\xa0', " ", content)
    content_length = len(content)

    for url_path in remove_before:
        if url.find(url_path) != -1:
            for regex in remove_before[url_path]:
                content = remove_before_regex(content, regex)
                content_length = len(content)

    for url_path in remove_after:
        if url.find(url_path) != -1:
            if url_path in remove_after:  # Additional check
                for regex in remove_after[url_path]:
                    content = remove_last_occurrence_and_after(content, regex)
                    content_length = len(content)

    for url_path in remove_string:
        if url.find(url_path) != -1:
            if url_path in remove_string:  # Additional check
                for data_string in remove_string[url_path]:
                    content = content.replace(data_string, "")
                    content_length = len(content)

    for url_path in remove_string_regexp:
        if url.find(url_path) != -1:
            if url_path in remove_string_regexp:  # Additional check
                for regex in remove_string_regexp[url_path]:
                    content = remove_text_regex(content, regex)
                    content_length = len(content)

    content = re.sub(r'\n\s+\n', '\n\n', content)
    content = re.sub(r'\n\n+', '\n\n', content)
    content = re.sub(r'\n+$', '', content)
    content = re.sub(r'^\n+', '', content)
    content_length = len(content)

    return content