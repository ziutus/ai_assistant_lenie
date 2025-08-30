import re

# from webdocument_md_decode import logger

def remove_new_line_only_in_string(text, string):
    for wynik in re.finditer(string.replace("\n", " "), text.replace("\n", " ")):
        text = text[:wynik.start()] + string.replace("\n", " ") + text[wynik.end():]
    return text


def get_images_with_links_md(markdown_text):
    regex = r'\!\[(.*?)\]\((.*?)\)'
    matches = re.findall(regex, markdown_text, re.DOTALL)

    extracted_images = []
    updated_text = markdown_text
    for i, match in enumerate(matches):
        alt_text_original = match[0]
        image = {
            "alt_text": match[0].replace("\n", " "),
            "url": match[1],
            "description": "",
            "owner": ""
        }

        markdown_text_tmp = markdown_text.replace("\n", " ")
        wystapienia = re.findall(image["alt_text"], markdown_text_tmp, re.DOTALL)
        liczba_wystapien = len(wystapienia)

        # logger.debug(f"Tekst szukany występuje {liczba_wystapien} razy.")

        if liczba_wystapien > 1:
            markdown_text = re.sub(alt_text_original, alt_text_original.replace("\n", " "), markdown_text, 1, re.DOTALL)
            markdown_text = remove_new_line_only_in_string(markdown_text, alt_text_original)


        regex_reach = rf'\!\[{re.escape(image["alt_text"])}\]\({re.escape(image["url"])}\)(.*?){re.escape(image["alt_text"])}'
        found_reach = re.search(regex_reach, markdown_text, re.DOTALL)

        if found_reach:
            # logger.debug("Found reach")
            image["description"] = image["alt_text"]
            image["owner"] = found_reach.group(1)

            markdown_text = markdown_text.replace(image["owner"], image["owner"].replace("\n", " "))
            image["owner"] = image["owner"].replace("\n", " ")


            tmp_to_replace = rf'\!\[{re.escape(image["alt_text"])}\]\({re.escape(image["url"])}\)\s*{re.escape(image["owner"])}\s*{re.escape(image["alt_text"])}'
            tmp_replace = f'picture({i}):"{image["alt_text"]}"'
            markdown_text = re.sub(tmp_to_replace, tmp_replace, markdown_text, 1, re.DOTALL)
        # else:
            # logger.debug("Not found reach")
        image["url"] = image["url"].replace("\n", "")
        extracted_images.append(image)

    return markdown_text, extracted_images


def links_correct(text):
    text_new = ""
    inside_link = False
    i=0
    while i < len(text):
        if text[i] == "h" and text[i+1] == "t" and text[i+2] == "t" and text[i+3] == "p" and text[i+4] == "s" and \
            text[i+5] == ":" and text[i+6] == "/" and text[i+7] == "/":
            inside_link = True
            i+=8
            text_new = text_new + "https://"
            continue

        if inside_link and text[i] == " " or text[i] == ")" or text[i] == "]":
            inside_link = False

        if inside_link and text[i] == '\r' and text[i+1] == '\n':
            i+=2
            continue

        if inside_link and text[i] == '\n':
            i+=1
            continue

        if inside_link and text[i] == ' ':
            i+=1
            continue

        text_new = text_new + text[i]
        i += 1

    return text_new


def md_get_images_as_links(md_text, clean_markdown=True):
    lines = md_text.split("\n")
    extracted_links = []
    extracted_images = []
    for line in lines:
        links_with_images = re.findall(r'\[\!\[(.*?)\]\((.*?)\)\]\((.*?)\)', line)
        if len(links_with_images) > 0:
            print("Found image as link")
            for link_with_image in links_with_images:
                link = {
                    "image_alt_text": link_with_image[0],
                    "image_url": link_with_image[1],
                    "url": link_with_image[2]
                }
                image = {
                    "alt_text": link_with_image[0],
                    "url": link_with_image[1]
                }
                extracted_links.append(link)
                extracted_images.append(image)
                replace_me = f"[![{link['image_alt_text']}]({link['image_url']})]({link['url']})"
                line = line.replace(replace_me, "")

                if clean_markdown:
                    md_text = md_text.replace(replace_me, "")

    return md_text, extracted_links, extracted_images


def process_markdown_and_extract_links(md_text):

    lines = md_text.split("\n")
    extracted_links = []
    for line in lines:
        links = re.findall(r'\[(.*?)\]\((.*?)\)', line)
        for i, link in enumerate(links):
            print(f"{i}: {link[0]}, {link[1]}")
            # md_text = remove_new_line_only_in_string(md_text, link[0])
            link_desc = link[0].replace("\n", " ")
            replace_text = f"[{link_desc}]({link[1]})"
            md_text = md_text.replace(replace_text, f"link[{len(extracted_links)}]:{link[0]}", 1)
            extracted_links.append({"text": link_desc, "link": link[1]})

    return md_text, extracted_links


def md_square_brackets_in_one_line(text):
    is_in_brackets = False
    text_new = ""
    level = 0

    for i, char in enumerate(text):
        if char == '[':
            is_in_brackets = True
            text_new += char
            level += 1
            continue
        elif char == ']':
            text_new += char
            level -= 1
            if level == 0:
                is_in_brackets = False
            continue
        elif char == "\n" and is_in_brackets and level > 0:
            text_new += " "
            continue
        else:
            text_new += char

    return text_new


def md_split_for_emb(part, split_limit=200, level=0):
    parts = []

    if level == 5:
        parts = split_text_by_paragraphs(part, split_limit)
        return parts

    if level == 0:
        delimiter = "\n# "
        splitter = "---split---\n# "
    elif level == 1:
        delimiter = "\n## "
        splitter = "---split---\n## "
    elif level == 2:
        delimiter = "\n### "
        splitter = "---split---\n### "
    elif level == 3:
        delimiter = "\n**"
        splitter = "---split---\n**"
    elif level == 4:
        delimiter = "\n— **"
        splitter = "---split---\n— **"
    else:
        return [part]

    word_count = len(part.split())
    if word_count < split_limit:
        return [part]

    parts_tmp = part.replace(delimiter, splitter)
    parts_tmp = parts_tmp.split("---split---")
    for part in parts_tmp:
        result = md_split_for_emb(part, split_limit, level + 1)
        parts.extend(result)
    return parts


def split_text_by_sentences(text, max_words=200):
    separatory = ['. ', '! ', '? ']
    wzorzec = '|'.join(map(re.escape, separatory))

    # Dzielimy tekst
    fragmenty = re.split(wzorzec, text)

    # Usuwamy puste elementy
    fragmenty = [fragment for fragment in fragmenty if fragment]

    for fragment in fragmenty:
        if len(fragment.split()) > max_words:
            raise "Please corect text first, there is no possiblity to split text by sentences"

    return fragmenty


def split_text_by_paragraphs(text, max_words=200):
    word_count = len(text.split())

    # If text is short enough, return it as a single-element list
    if word_count <= max_words:
        return [text]

    # Try to split text into paragraphs
    paragraphs = [p for p in text.split('\n\n') if p.strip()]

    parts = []
    part = ""
    for paragraph in paragraphs:
        if len(paragraph.split()) > max_words:
            parts_tmp = split_text_by_sentences(paragraph, max_words)
            parts.extend(parts_tmp)
            continue

        if len(part.split()) + len(paragraph.split()) > max_words:
            parts.append(part)
            part = paragraph
            continue

        part += paragraph + "\n"

    parts.append(part)

    return parts

def md_remove_markdown(text):
    lines2 = []

    for line in text.splitlines():
        if line.startswith("# "):
            line = line.replace("# ", "")
        if line.startswith("## "):
            line = line.replace("## ", "")
        if line.startswith("### "):
            line = line.replace("### ", "")
        if line.startswith("#### "):
            line = line.replace("#### ", "")
        if line.startswith("##### "):
            line = line.replace("##### ", "")
        lines2.append(line)
    text = "\n".join(lines2)

    return text
