from openai import OpenAI

from library.models.embedding_result import EmbeddingResult


API_BASE = "https://api.ark-labs.cloud/api/v1"


def _get_api_key():
    from library.config_loader import load_config
    cfg = load_config()
    key = cfg.get("ARKLABS_API_KEY")
    if not key:
        raise RuntimeError("ARKLABS_API_KEY is not set")
    return key


def get_embedding(text: str, model: str = "BAAI/bge-m3") -> EmbeddingResult:
    client = OpenAI(api_key=_get_api_key(), base_url=API_BASE)

    result = EmbeddingResult(text=text, model_id=model)

    response = client.embeddings.create(
        input=text,
        model=model
    )

    result.status = "success"
    result.embedding = response.data[0].embedding

    return result
