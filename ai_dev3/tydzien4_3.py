import os

from markitdown import MarkItDown
import requests
from urllib.parse import urlparse

# needed_answers = {
#     "01": "Podaj adres mailowy do firmy SoftoAI",
#     "02": "Jaki jest adres interfejsu webowego do sterowania robotami zrealizowanego dla klienta jakim jest firma BanAN?",
#     "03": "Jakie dwa certyfikaty jako\u015bci ISO otrzyma\u0142a firma SoftoAI?"
# }



def url_to_markdown(url, cache_dir, default_file="/index.html", force=False):
    url_parsed = urlparse(url)
    filepath = url_parsed.path

    if filepath == "/":
        filepath = default_file

    filepath = filepath.replace("/", "_")

    if not os.path.exists(f"{cache_dir}{filepath}") or force:
        response = requests.get(url)

        with open(f"{cache_dir}{filepath}", "w", encoding="utf-8") as file:
            file.write(response.text)

    filepath_md = filepath.replace(".html", ".md").replace(".htm", ".md")
    if not filepath_md.endswith(".md"):
        filepath_md += ".md"

    if not os.path.exists(f"{cache_dir}{filepath_md}") or force:
        md = MarkItDown()
        result = md.convert(f"{cache_dir}{filepath}")

        with open(f"{cache_dir}{filepath_md}", "w", encoding="utf-8") as file:
            file.write(result.text_content)

    with open(f"{cache_dir}{filepath_md}", "r", encoding="utf-8") as file:
        return file.read()


cache_dir = "tmp/tydzien4_3"
url = "https://softo.ag3nts.org/blog/sukcesy-softoai"

md_content = url_to_markdown(url, cache_dir)

print(md_content)

exit(0)