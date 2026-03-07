import requests
from library.config_loader import load_config
from library.models.embedding_results import EmbeddingResults
from library.models.embedding_result import EmbeddingResult

API_BASE = "https://api-sherlock.cloudferro.com/openai/v1/"


def _get_api_key() -> str:
    cfg = load_config()
    return cfg.require("CLOUDFERRO_SHERLOCK_KEY")


def sherlock_create_embeddings(texts, model="BAAI/bge-multilingual-gemma2")-> EmbeddingResults :
    """
    Tworzy embeddingi dla podanej listy tekstów używając określonego modelu.

    Args:
        texts (list): Lista tekstów do przetworzenia na embeddingi
        model (str): Identyfikator modelu do embeddingu

    Returns:
        EmbeddingResults: Odpowiedź API z embeddingami
    """
    embedding = EmbeddingResults(text=texts)

    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json"
    }

    payload = {
        "input": texts,
        "model": model
    }

    try:
        response = requests.post(
            f"{API_BASE}embeddings",
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

def sherlock_create_embedding(text, model="BAAI/bge-multilingual-gemma2")-> EmbeddingResult :
    embedding = EmbeddingResult(text=text)
    response = sherlock_create_embeddings([text], model)

    embedding.status_code = response.status_code
    embedding.model_id = response.model_id

    if response.status_code == 200:
        embedding.prompt_tokens = response.prompt_tokens
        embedding.total_tokens = response.total_tokens
        embedding.embedding = response.embedding[0]['embedding']
    else:
        embedding.error = response.error_message

    return embedding
