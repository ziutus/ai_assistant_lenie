from openai import OpenAI

from library.embedding_results import EmbeddingResult


def get_embedding(text: str) -> EmbeddingResult:
    client = OpenAI()

    model_id = "text-embedding-ada-002"

    result = EmbeddingResult(text=text, model_id=model_id)

    response = client.embeddings.create(
        input=text,
        model=model_id
    )

    result.status = "success"
    result.embedding = response.data[0].embedding

    return result
