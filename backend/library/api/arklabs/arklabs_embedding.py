from openai import OpenAI

from library.models.embedding_result import EmbeddingResult
from library.api.arklabs.config import get_arklabs_config


def get_embedding(text: str, model: str = "BAAI/bge-m3") -> EmbeddingResult:
    api_key, base_url = get_arklabs_config()
    client = OpenAI(api_key=api_key, base_url=base_url)

    result = EmbeddingResult(text=text, model_id=model)

    response = client.embeddings.create(
        input=text,
        model=model
    )

    result.status = "success"
    result.embedding = response.data[0].embedding

    return result
