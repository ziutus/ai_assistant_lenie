import time

from library.models.embedding_result import EmbeddingResult


embedding_models = {"amazon.titan-embed-text-v1", "amazon.titan-embed-text-v2:0", "text-embedding-ada-002",
                    "BAAI/bge-multilingual-gemma2", "intfloat/e5-mistral-7b-instruct", "BAAI/bge-m3"}


_SHERLOCK_MODELS = {"BAAI/bge-multilingual-gemma2", "intfloat/e5-mistral-7b-instruct"}
_SHERLOCK_EMBEDDINGS_ENDPOINT = "https://api-sherlock.cloudferro.com/openai/v1/embeddings"


def _record_sherlock_embedding_usage(response, model: str, latency_ms: int) -> None:
    """Persist one observation per CloudFerro embedding batch.

    The recorder inherits document/job/run context, so this makes embedding
    failures visible both in a document's cost history and in service status.
    Recording is deliberately best-effort and cannot change embedding results.
    """
    success = response.status_code == 200 and bool(response.embedding)
    error_code = None
    if not success:
        error_code = f"HTTP_{response.status_code}" if response.status_code > 0 else "EmbeddingRequestError"
    try:
        from library.llm_usage.recorder import record_llm_usage

        record_llm_usage(
            operation="embedding",
            provider="cloudferro",
            model=model,
            prompt_tokens=response.prompt_tokens,
            total_tokens=response.total_tokens,
            endpoint=_SHERLOCK_EMBEDDINGS_ENDPOINT,
            success=success,
            error_code=error_code,
            latency_ms=latency_ms,
        )
    except (SystemExit, Exception):
        # Keep embedding generation available when observability storage is down.
        pass


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

        started = time.monotonic()
        try:
            response = sherlock_create_embeddings(texts, model)
        except Exception:
            # The production client normally converts transport exceptions to
            # an error result, but retain an audit record for unexpected ones.
            try:
                from library.llm_usage.recorder import record_llm_usage

                record_llm_usage(
                    operation="embedding", provider="cloudferro", model=model,
                    endpoint=_SHERLOCK_EMBEDDINGS_ENDPOINT, success=False,
                    error_code="EmbeddingRequestException",
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            except (SystemExit, Exception):
                pass
            raise
        _record_sherlock_embedding_usage(
            response, model, int((time.monotonic() - started) * 1000),
        )
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
        # Reuse the batch path even for one input so every CloudFerro embedding
        # request has the same usage/status observation.
        return get_embeddings(model, [text])[0]
    elif model in ["BAAI/bge-m3"]:
        import library.api.arklabs.arklabs_embedding as arklabs_embedding
        return arklabs_embedding.get_embedding(text, model)
    else:
        raise Exception(f"DEBUG: Error, not supported model {model}")
