import boto3

# Konfiguracja klienta Rekognition
client = boto3.client('rekognition')

# Ścieżka do pliku
image_path = "tmp/tydzien2_5/arxiv-draft/fruit01.png"

# Otwieranie pliku obrazu
with open(image_path, "rb") as image_file:
    image_bytes = image_file.read()

# Wysyłanie obrazu do usługi Rekognition
response = client.detect_labels(
    Image={'Bytes': image_bytes},
    MaxLabels=20,  # Ilość etykiet do wykrycia
    MinConfidence=75  # Minimalne prawdopodobieństwo
)

# Wyświetlenie wyników
for label in response['Labels']:
    print(f"Nazwa: {label['Name']}, Pewność: {label['Confidence']:.2f}%")