import os
import requests
from markdownify import markdownify as md
from bs4 import BeautifulSoup
from library.ai import ai_describe_image
import base64
from dotenv import load_dotenv
from library.transcript import transcript


load_dotenv()

def create_txt_path(image_path):
    """
    Funkcja zmienia rozszerzenie pliku na '.txt', pozostawiając resztę ścieżki bez zmian.

    :param image_path: Ścieżka do pliku oryginalnego (string)
    :return: Ścieżka do nowego pliku z rozszerzeniem '.txt' (string)
    """
    base_path, _ = os.path.splitext(image_path)  # Oddzielenie ścieżki bazowej od rozszerzenia
    return f"{base_path}.txt"


def download_file(url, cache_dir, page_id, file_name, force=False) -> str:
    page_dir = f"{cache_dir}/{page_id}"
    os.makedirs(page_dir, exist_ok=True)

    file_name_full = f"{page_dir}/{file_name}"

    if not os.path.exists(f"{page_dir}/{file_name}") and not force:
        print(f"Debug: downloading {full_link}")
        response = requests.get(url)

        with open(f"{page_dir}/{file_name}", 'wb') as file:
            file.write(response.content)
    else:
        print(f"Debug: skipping {full_link}")

    return file_name_full


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
print("png files Links:", multi_media_links)
for link in png_links:
    full_link = f"{url_base}/{link}"

    full_file = f"{cache_dir}/{page_id}/{os.path.basename(link)}"
    print(f"full_file: {full_file}")

    if not os.path.exists(full_file):
        media_file = download_file(full_link, cache_dir, page_id, os.path.basename(link))

        if full_file != media_file:
            print(f"Debug: something went wrong, {full_file} != {media_file}")
            exit(1)

    txt_path = create_txt_path(full_file)
    print(txt_path)

    if not os.path.exists(txt_path):
        print(f"Debug: txt file {txt_path} does not exist, creating it")

        with open(full_file, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        ai_image_description = ai_describe_image(base64_image, question="Co jest na obrazku?")
        print(ai_image_description.response_text)

        with open(txt_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(ai_image_description.response_text)

for link in mp3_links:
    full_link = f"{url_base}/{link}"

    full_file = f"{cache_dir}/{page_id}/{os.path.basename(link)}"
    print(f"full_file: {full_file}")

    if not os.path.exists(full_file):
        media_file = download_file(full_link, cache_dir, page_id, os.path.basename(link))

        if full_file != media_file:
            print(f"Debug: something went wrong, {full_file} != {media_file}")
            exit(1)

    txt_path = create_txt_path(full_file)
    print(txt_path)

    if not os.path.exists(txt_path):
        print(f"will prepare transcription for file {link}")
        print(f"Debug: txt file {txt_path} does not exist, creating it")

        transcript_text = transcript(full_file, "mp3", language_code="pl", provider="assemblyai")
        print(transcript_text)
        with open(txt_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(transcript_text)

