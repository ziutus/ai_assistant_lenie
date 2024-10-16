import hashlib
import re


def get_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def remove_last_occurrence_and_after(text: str, regex: str) -> str:
    matches = [m for m in re.finditer(regex, text)]
    if matches:
        last_match = matches[-1]
        return text[:last_match.start()]
    else:
        return text


def remove_before_regex(text: str, regex: str) -> str:
    match = re.search(regex, text)
    if match:
        # zwróć wszystko po dopasowanym wzorcu
        return text[match.end():].strip()
    else:
        return text


def remove_after_regex(text: str, regex: str) -> str:
    match = re.search(regex, text)
    if match:
        return text[:match.end()].strip()
    else:
        return text


def remove_text_regex(text: str, regex: str) -> str:
    return re.sub(regex, "", text)


def split_text_for_embedding(text, paragraph_titles=[], max_words_in_line=300, max_characters_in_line=1000):
    sentences2 = []
    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        text_tmp = ""
        for line in paragraph.splitlines():
            if line in paragraph_titles:
                text_tmp += line + "\n"
            else:
                text_tmp += line + " "
        paragraph = text_tmp

        if len(paragraph) < max_characters_in_line:
            text = ""
            for line in paragraph.splitlines():
                if line in paragraph_titles:
                    text += line + "\n"
                else:
                    text += line
            if len(text) > 0:
                sentences2.append(text)
            continue

        sentences = paragraph.split(".")

        for sentence in sentences:
            sentence = sentence.strip()
            while len(sentence) > 0:
                words = sentence.split(" ")
                if len(words) <= max_words_in_line:
                    sentences2.append(sentence)
                    sentence = ""
                    continue

                word_nb = 1
                word_upper_nb = 1
                for word in words:
                    if len(word) > 0:
                        if word[0].isupper():
                            if word_nb > max_words_in_line:
                                break
                            word_upper_nb = word_nb
                    word_nb += 1

                new_string = " ".join(words[:word_upper_nb - 1])
                if len(new_string) > 0:
                    new_string2 = new_string.strip()
                    sentences2.append(new_string2)

                sentence = sentence.replace(new_string, "")
                sentence = sentence.strip()

    return '\n\n'.join(sentences2)
