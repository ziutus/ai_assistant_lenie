import re

class DocumentMarkDown:
    def __init__(self):
        self.url = ""
        self.text_md = ""
        self.links = []
        self.images = []

    def extract_images_with_references(self, ignored_images):

        # Regex do wyłapywania zdjęć w Markdown
        image_pattern = r'!\[(.*?)\]\((.*?)\)|!\[\]\((.*?)\)'

        # Znajdź wszystkie obrazy w Markdown (także z pustymi opisami)
        matches = re.findall(image_pattern, self.text_md)

        # Wyciągnij informacje o zdjęciach (alt i URL)
        images = []
        for match in matches:
            alt_text = match[0] if match[0] else "Brak opisu"
            image_url = match[1] if match[1] else match[2]

            if image_url in ignored_images:
                print("Ignoring image")
                continue

            images.append((alt_text, image_url))

        # Zamień obrazy na odwołania liczbowe [1], [2], itd.
        def replace_with_reference(match):
            # Ignoruj obrazy także podczas zamiany w tekście
            image_url = match.group(2) or match.group(3)
            if image_url in ignored_images:
                return ""  # Usuń z tekstu Markdown

            index = len(images_references) + 1
            images_references.append((index, match.group(1) or "Brak opisu", image_url))
            return f"[{index}]"

        images_references = []
        self.text_md = re.sub(image_pattern, replace_with_reference, self.text_md)

        self.images = images_references
        # Generuj numerowaną listę zdjęć w formacie Markdown
        # image_list = "\n".join([f"{index}. **{alt}**: {url}" for index, alt, url in images_references])

        # Połącz oczyszczony tekst z obrazami w formie listy
        # final_output = f"{cleaned_text.strip()}\n\n### Lista zdjęć:\n{image_list}"

        # return final_output

    def extract_references_with_numbered_links(self):
        # Regex do wyłapywania fraz "Zobacz także:[tekst odnośnika](url)"
        reference_pattern = r'Zobacz także:\[(.*?)\]\((.*?)\)'

        # Znajdź wszystkie dopasowania w Markdown
        matches = re.findall(reference_pattern, self.text_md)

        # Wyciągnij informacje o odnośnikach (tekst i URL)
        references = []
        for match in matches:
            ref_text = match[0]
            ref_url = match[1]
            references.append((ref_text, ref_url))

        # Zamień odnośniki w tekście na odwołania liczbowe [1], [2], itd.
        def replace_with_reference(match):
            index = len(references_replaced) + 1
            references_replaced.append((index, match.group(1), match.group(2)))
            return f"[{index}]"

        references_replaced = []
        self.text_md = re.sub(reference_pattern, replace_with_reference, self.text_md)

        self.links = references_replaced

        return True

