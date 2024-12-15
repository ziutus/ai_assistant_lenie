import os
import requests
from markdownify import markdownify as md
from bs4 import BeautifulSoup


def download_file(url, cache_dir, page_id, file_name, force=False):
    page_dir = f"{cache_dir}/{page_id}"
    os.makedirs(page_dir, exist_ok=True)

    if not os.path.exists(f"{page_dir}/{file_name}") and not force:
        print(f"Debug: downloading {full_link}")
        response = requests.get(url)

        with open(f"{page_dir}/{file_name}", 'wb') as file:
            file.write(response.content)
    else:
        print(f"Debug: skipping {full_link}")


cache_dir = "tmp/tydzien2_5"
page_id = "arxiv-draft"
file_name = "arxiv-draft.html"

file_path = f"{cache_dir}/{page_id}/arxiv-draft.html"
file_path_md = f"{cache_dir}/arxiv-draft.md"

url_base = 'https://centrala.ag3nts.org/dane'
url = f"{url_base}/arxiv-draft.html"

if not os.path.exists(file_path):
    print("Downloading source page")
    download_file(url, cache_dir, "arxiv-draft", file_name)

    print("Converting to markdown")
    with open(file_path, encoding='utf-8') as f:
        html = f.read()

    markdown = md(html)
    with open(file_path_md, "w", encoding='utf-8') as f:
        f.write(markdown)

print("Downloading images and links")
with open(file_path, 'r', encoding='utf-8') as file:
    html_content = file.read()

soup = BeautifulSoup(html_content, 'html.parser')

# Wyszukiwanie linków do plików PNG i MP3
png_links = [tag['src'] for tag in soup.find_all('img', src=True) if tag['src'].endswith('.png')]
mp3_links = [tag['href'] for tag in soup.find_all('a', href=True) if tag['href'].endswith('.mp3')]

multi_media_links = png_links + mp3_links

# Wyświetlenie linków
print("multimedia Links:", multi_media_links)
for link in multi_media_links:
    full_link = f"{url_base}/{link}"
    download_file(full_link, cache_dir, page_id, os.path.basename(link))
