import re

import requests
from bs4 import BeautifulSoup

from library.text_functions import remove_before_regex, remove_last_occurrence_and_after, remove_text_regex
import json

from library.models.webpage_parse_result import WebPageParseResult


def load_site_rules(file_path: str) -> dict:
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def download_raw_html(url: str) -> bytes | None:
    response = requests.get(url)

    if response.status_code == 200:
        return response.content
    else:
        return None


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

    site_rules = load_site_rules('data/site_rules.json')

    for url_path in site_rules:
        if url.find(url_path) != -1:
            for regex in site_rules[url_path]["remove_before"]:
                content = remove_before_regex(content, regex)
            for regex in site_rules[url_path]["remove_after"]:
                content = remove_last_occurrence_and_after(content, regex)
            for data_string in site_rules[url_path]["remove_string"]:
                content = content.replace(data_string, "")
            for regex in site_rules[url_path]["remove_string_regexp"]:
                content = remove_text_regex(content, regex)

    content = re.sub(r'\n\s+\n', '\n\n', content)
    content = re.sub(r'\n\n+', '\n\n', content)
    content = re.sub(r'\n+$', '', content)
    content = re.sub(r'^\n+', '', content)

    return content
