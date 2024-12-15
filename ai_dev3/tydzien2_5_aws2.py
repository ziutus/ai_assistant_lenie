import boto3
import os
import base64
import json

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

def ai_describe_image(base64_image, model_id="anthropic.claude-3-haiku-20240307-v1:0"):

    # Inicjalizacja klienta Bedrock
    session = boto3.Session()
    client_bedrock = session.client(
        service_name='bedrock-runtime',
        region_name=os.getenv("AWS_REGION", "us-east-1")  # Ustaw domyślny region na `us-east-1` jeśli nie podany
    )

    # Przygotowanie payloadu
    payload = {
        "modelId": "anthropic.claude-3-haiku-20240307-v1:0",
        "contentType": "application/json",
        "accept": "application/json",
        "body": json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                # Ustaw typ obrazu (zmień na `image/jpeg` w odpowiednich przypadkach)
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": "What's in this image?"
                        }
                    ]
                }
            ]
        })
    }

    # Wysłanie żądania do Bedrock Runtime
    response = client_bedrock.invoke_model(
        modelId=payload["modelId"],
        contentType=payload["contentType"],
        accept=payload["accept"],
        body=payload["body"]
    )

    # Obsługa odpowiedzi
    response_body = json.loads(response['body'].read().decode('utf-8'))
    # print("Odpowiedź modelu:", json.dumps(response_body, indent=4))
    response_text = response_body['content'][0]['text']

    return response_text


# Konwertowanie obrazu na Base64
with open(image_path, "rb") as image_file:
    base64_image = base64.b64encode(image_file.read()).decode("utf-8")

response_text = ai_describe_image(base64_image)
print(response_text)

txt_path = create_txt_path(image_path)
print(txt_path)

with open(txt_path, "w", encoding="utf-8") as txt_file:
    txt_file.write(response_text)

