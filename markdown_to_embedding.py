import os
import markdown
from bs4 import BeautifulSoup


def markdown_to_text(markdown_string):
    # Konwertujemy Markdown do HTML
    html = markdown.markdown(markdown_string)

    # Konwertujemy HTML do czystego tekstu
    soup = BeautifulSoup(html, "html.parser")
    text = ''.join(soup.findAll(string=True))

    return text


documents = ["6713"]
cache_directory = "tmp/markdown_output"

for document_id in documents:
    filname_json = f"{cache_directory}/{document_id}.json"

    if os.path.exists(f"{cache_directory}/{document_id}_manual.md"):
        print("Manual correction exist, using it")
        filename_md = f"{cache_directory}/{document_id}_manual.md"
    elif os.path.exists(f"{cache_directory}/{document_id}.md"):
        filename_md = f"{cache_directory}/{document_id}.md"
    else:
        print(f"No markdown files for document_id: {document_id}, skipping it")
        continue

    with open(filename_md, "r", encoding="utf-8") as file:
        markdown_text = file.read()

    text = markdown_to_text(markdown_text)
    with open(f"{cache_directory}/{document_id}.txt", "w", encoding="utf-8") as file:
        file.write(text)

    len_text = len(markdown_text)
    len_words = len(markdown_text.split())
    words_per_part = 200

    print("ilość znaków: ", len_text)
    print("ilość słów:", len_words)
    print(f"Tekst najlepiej podzielić na {round(len_words / words_per_part)} części")
    print(f"czysty tekst (znaków): {len(text)}")
    print(f"czysty tekst, ilość słów: {len(text.split())}")
    print(f"czysty tekst, podział: {round(len(text.split()) / words_per_part)}")
