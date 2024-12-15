import os
import base64

from library.ai import ai_describe_image

# Ścieżka do obrazu
image_path = "tmp/tydzien2_5/arxiv-draft/resztki.png"

def create_txt_path(image_path):
    """
    Funkcja zmienia rozszerzenie pliku na '.txt', pozostawiając resztę ścieżki bez zmian.

    :param image_path: Ścieżka do pliku oryginalnego (string)
    :return: Ścieżka do nowego pliku z rozszerzeniem '.txt' (string)
    """
    base_path, _ = os.path.splitext(image_path)  # Oddzielenie ścieżki bazowej od rozszerzenia
    return f"{base_path}.txt"


# Konwertowanie obrazu na Base64
with open(image_path, "rb") as image_file:
    base64_image = base64.b64encode(image_file.read()).decode("utf-8")

response_text = ai_describe_image(base64_image, question="Co jest na obrazku?")
print(response_text)

txt_path = create_txt_path(image_path)
print(txt_path)

with open(txt_path, "w", encoding="utf-8") as txt_file:
    txt_file.write(response_text)

