import library.api.aws.bedrock_embedding as amazon_bedrock
import library.api.openai.openai_embedding as openai_embedding
from library.api.cloudferro.sherlock.sherlock_embedding import sherlock_create_embedding
from library.models.embedding_result import EmbeddingResult


embedding_models = {"amazon.titan-embed-text-v1", "amazon.titan-embed-text-v2:0", "text-embedding-ada-002",
                    "BAAI/bge-multilingual-gemma2"}


def embedding_need_translation(model: str) -> bool:
    if model not in embedding_models:
        raise Exception(f"DEBUG: Error, no model info for text {model}")

    if model in ["amazon_bedrock", "amazon.titan-embed-text-v1"]:
        return False
    elif model in ["amazon.titan-embed-text-v2:0"]:
        return False
    elif model in ["BAAI/bge-multilingual-gemma2"]:
        return False
    elif model in ["openai_embedding", "text-embedding-ada-002"]:
        return True
    else:
        raise Exception(f"DEBUG: Error, no model info for text {model}")


def get_embedding(model: str, text: str) -> EmbeddingResult:
    if model not in embedding_models:
        raise Exception(f"DEBUG: Error, no model info for text {model}")

    if model in ["amazon_bedrock", "amazon.titan-embed-text-v1"]:
        return amazon_bedrock.get_embedding(text)
    elif model in ["amazon.titan-embed-text-v2:0"]:
        return amazon_bedrock.get_embedding2(text)
    elif model in ["openai_embedding", "text-embedding-ada-002"]:
        return openai_embedding.get_embedding(text)
    elif model in ["BAAI/bge-multilingual-gemma2"]:
        return sherlock_create_embedding(text, model)
    else:
        raise Exception(f"DEBUG: Error, not supported model {model}")
