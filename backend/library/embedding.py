from library.models.embedding_result import EmbeddingResult


embedding_models = {"amazon.titan-embed-text-v1", "amazon.titan-embed-text-v2:0", "text-embedding-ada-002",
                    "BAAI/bge-multilingual-gemma2", "intfloat/e5-mistral-7b-instruct", "BAAI/bge-m3"}


_SHERLOCK_MODELS = {"BAAI/bge-multilingual-gemma2", "intfloat/e5-mistral-7b-instruct"}


def get_embeddings(model: str, texts: list[str]) -> list[EmbeddingResult]:
    """Batch variant of get_embedding — one API call where the provider supports it.

    CloudFerro Sherlock embeds the whole list in a single request; other
    providers fall back to one get_embedding call per text (which also
    validates the model name). Always returns one EmbeddingResult per input
    text, in input order.
    """
    if not texts:
        return []

    if model in _SHERLOCK_MODELS:
        from library.api.cloudferro.sherlock.sherlock_embedding import sherlock_create_embeddings

        response = sherlock_create_embeddings(texts, model)
        if response.status_code != 200 or not response.embedding:
            error = getattr(response, "error", None) or response.error_message or f"HTTP {response.status_code}"
            return [
                EmbeddingResult(text=text, model_id=model, status="error", error_message=str(error))
                for text in texts
            ]
        vectors: list = [None] * len(texts)
        for position, item in enumerate(response.embedding):
            index = item.get("index", position) if isinstance(item, dict) else position
            if isinstance(index, int) and 0 <= index < len(vectors):
                vectors[index] = item["embedding"] if isinstance(item, dict) else item
        results = []
        for text, vector in zip(texts, vectors):
            if vector is None:
                results.append(EmbeddingResult(
                    text=text, model_id=response.model_id, status="error",
                    error_message="missing embedding in batch response",
                ))
            else:
                result = EmbeddingResult(text=text, model_id=response.model_id, embedding=vector, status="success")
                result.status_code = 200
                results.append(result)
        return results

    return [get_embedding(model, text) for text in texts]


def get_embedding(model: str, text: str) -> EmbeddingResult:
    if model not in embedding_models:
        raise Exception(f"DEBUG: Error, no model info for text {model}")

    if model in ["amazon_bedrock", "amazon.titan-embed-text-v1"]:
        import library.api.aws.bedrock_embedding as amazon_bedrock
        return amazon_bedrock.get_embedding(text)
    elif model in ["amazon.titan-embed-text-v2:0"]:
        import library.api.aws.bedrock_embedding as amazon_bedrock
        return amazon_bedrock.get_embedding2(text)
    elif model in ["openai_embedding", "text-embedding-ada-002"]:
        import library.api.openai.openai_embedding as openai_embedding
        return openai_embedding.get_embedding(text)
    elif model in ["BAAI/bge-multilingual-gemma2", "intfloat/e5-mistral-7b-instruct"]:
        from library.api.cloudferro.sherlock.sherlock_embedding import sherlock_create_embedding
        return sherlock_create_embedding(text, model)
    elif model in ["BAAI/bge-m3"]:
        import library.api.arklabs.arklabs_embedding as arklabs_embedding
        return arklabs_embedding.get_embedding(text, model)
    else:
        raise Exception(f"DEBUG: Error, not supported model {model}")
