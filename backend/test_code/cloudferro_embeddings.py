import os
import requests
from dotenv import load_dotenv
from pprint import pprint
from library.embedding_results import EmbeddingResults

load_dotenv()

# Ustawienie klucza API i niestandardowego URL dla CloudFerro Sherlock API
api_key = os.environ["CLOUDFERRO_SHERLOCK_KEY"]
api_base = "https://api-sherlock.cloudferro.com/openai/v1/"


def create_embeddings(texts, model="BAAI/bge-multilingual-gemma2")-> EmbeddingResults :
    """
    Tworzy embeddingi dla podanej listy tekstów używając określonego modelu.

    Args:
        texts (list): Lista tekstów do przetworzenia na embeddingi
        model (str): Identyfikator modelu do embeddingu

    Returns:
        dict: Odpowiedź API z embeddingami
    """
    embedding = EmbeddingResults(text=texts)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "input": texts,
        "model": model
    }

    try:
        response = requests.post(
            f"{api_base}embeddings",
            headers=headers,
            json=payload
        )

        if response.status_code == 200:
            result = response.json()

            embedding.status_code = response.status_code
            embedding.model_id = result['model']
            embedding.prompt_tokens = result['usage']['prompt_tokens']
            embedding.total_tokens = result['usage']['total_tokens']
            embedding.embedding = result['data']

            return embedding
        else:
            print(f"Błąd: {response.status_code} - {response.text}")
            embedding.error = response.text
            embedding.status_code = response.status_code
            return embedding

    except Exception as e:
        print(f"Wystąpił błąd podczas komunikacji z API: {e}")
        embedding.error = str(e)
        embedding.status_code = -1
        return embedding


# Przykład użycia
if __name__ == "__main__":
    # Przykładowa lista tekstów do embeddingu
    przykładowe_teksty = [
        "To jest przykładowy tekst do embeddingu.",
        "Embeddingi są używane w wielu aplikacjach NLP."
    ]

    # Stworzenie embeddingów
    embedds = create_embeddings(przykładowe_teksty)

    print(embedds.status_code)

    if embedds.status_code == 200:
        print("Embeddingi zostały wygenerowane pomyślnie!")
        print(f"Liczba wygenerowanych embeddingów: {len(embedds.embedding)}")
        print(f"Wymiar embeddingów: {len(embedds.embedding[0]['embedding'])}")

        # Opcjonalnie - wyświetlenie pierwszych kilku wartości pierwszego embeddingu
        print("\nPierwszy embedding (pierwsze 5 wartości):")
        print(embedds.embedding[0]['embedding'][:5])

        # Opcjonalnie - informacje o użytych tokenach
        print(f"\nZużycie tokenów: {embedds.total_tokens} tokenów")
    else:
        pprint(embedds)
