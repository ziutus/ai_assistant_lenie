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
            md_text = md_text.replace(replace_text, f"link[{len(extracted_links)}]:\"{link[0]}\"", 1)
            extracted_links.append({"text": link_desc, "link": link[1]})

    return md_text, extracted_links


def process_markdown_and_extract_links_old(md_text):
    # Wyrażenie regularne do wyszukiwania linków
    pattern = re.compile(r'\[(.*?)\]\((.*?)\)')

    links = pattern.findall(md_text)
    extracted_links = [{"text": text, "link": url} for text, url in links]

    # Zastąpienie linków tekstami link:ID
    for i in range(len(links)):
        md_text = md_text.replace(f'[{links[i][0]}]({links[i][1]})', f'{extracted_links[i]["text"]}')

    return md_text, extracted_links


def md_square_brackets_in_one_line(text):
    is_in_brackets = False
    text_new = ""

    for i, char in enumerate(text):
        if char == '[':
            is_in_brackets = True
            text_new += char
            continue
        elif char == ']':
            is_in_brackets = False
            text_new += char
            continue
        elif char == "\n" and is_in_brackets:
            text_new += " "
            continue
        else:
            text_new += char

    return text_new
