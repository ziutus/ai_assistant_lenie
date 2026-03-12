from library.models.embedding_result import EmbeddingResult


embedding_models = {"amazon.titan-embed-text-v1", "amazon.titan-embed-text-v2:0", "text-embedding-ada-002",
                    "BAAI/bge-multilingual-gemma2", "intfloat/e5-mistral-7b-instruct",
                    "dunzhang/stella_en_1.5B_v5", "BAAI/bge-m3"}


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
    elif model in ["BAAI/bge-multilingual-gemma2", "intfloat/e5-mistral-7b-instruct",
                    "dunzhang/stella_en_1.5B_v5"]:
        from library.api.cloudferro.sherlock.sherlock_embedding import sherlock_create_embedding
        return sherlock_create_embedding(text, model)
    elif model in ["BAAI/bge-m3"]:
        import library.api.arklabs.arklabs_embedding as arklabs_embedding
        return arklabs_embedding.get_embedding(text, model)
    else:
        raise Exception(f"DEBUG: Error, not supported model {model}")
