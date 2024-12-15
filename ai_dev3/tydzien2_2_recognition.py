import boto3
from pprint import pprint

# Inicjalizacja klienta rekognition
rekognition = boto3.client('rekognition', region_name='us-east-1')  # Zmień region, jeśli wymagane


# Funkcja analizująca obraz i ekstrakcję tekstu
def extract_text_from_image(image_path):
    # Wczytaj obraz w formacie JPG
    with open(image_path, 'rb') as image_file:
        image_bytes = image_file.read()

    # Wywołanie API AWS Rekognition do wykrycia tekstu
    response = rekognition.detect_text(
        Image={'Bytes': image_bytes}
    )

    return response


if __name__ == "__main__":
    # Ścieżka do obrazu mapy
    image_path = "tmp/mapa.jpeg"

    # Ekstrakcja tekstu
    result = extract_text_from_image(image_path)

    # Wypisz wykryty tekst (typy i treść)
    detected_texts = [text['DetectedText'] for text in result['TextDetections']]
    pprint(detected_texts)

    # Alternatywna prezentacja wyników
    print("\nWykryty tekst (potencjalne nazwy ulic):")
    for text in detected_texts:
        print(f"- {text}")