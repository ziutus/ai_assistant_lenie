import library.api.aws.bedrock_ask
import library.api.openai.openai_my
from library.models.ai_response import AiResponse
from library.api.cloudferro.sherlock.sherlock import sherlock_get_completion
import library.api.google.google_vertexai as google_vertexai

def get_all_models_info():
    return {
        "amazon.titan-tg1-large": {"need_translation": True},
        "gpt-4": {"need_translation": True},
        "gpt-3.5-turbo": {"need_translation": True},
        "Bielik-11B-v2.3-Instruct": {"need_translation": False},
        "gemini-2.0-flash-lite-001": {"need_translation": False},
    }


def ai_model_need_translation_to_english(model: str) -> bool:
    models_info = get_all_models_info()
    if model in models_info:
        return models_info[model]["need_translation"]

    raise Exception(f"DEBUG: Error, no model info for text {model}")


def ai_ask(query: str, model: str, temperature: float = 0.7, max_token_count: int = 4096, top_p: float = 0.9) \
        -> AiResponse:

    if model in ["gpt-3.5-turbo", "gpt-3.5-turbo-16k"]:
        if len(query) < 8000:
            model = "gpt-3.5-turbo"
        elif len(query) < 16000:
            model = "gpt-3.5-turbo-16k"
        else:
            raise Exception("To long text for gpt-3.5 models")
        ai_response = AiResponse(query=query, model=model)
        ai_response.model = model

        response = library.api.openai.openai_my.OpenAIClient.get_completion(query, model)

        if isinstance(response, bytes):
            response = response.decode('utf-8')

        ai_response.response_text = response
        return ai_response
    if model in ["gpt-4", "gpt-4o", "gpt-4o-2024-05-13"]:
        response = library.api.openai.openai_my.OpenAIClient.get_completion(query, model)
        ai_response = AiResponse(query=query, model=model)

        if isinstance(response, bytes):
            response = response.decode('utf-8')

        ai_response.response_text = response
        return ai_response

    elif model in ["gpt-4o-mini"]:
        response = library.api.openai.openai_my.OpenAIClient.get_completion(query, model)
        ai_response = AiResponse(query=query, model=model)

        if isinstance(response, bytes):
            response = response.decode('utf-8')

        ai_response.response_text = response
        return ai_response

    elif model in ('amazon.titan-tg1-large', 'amazon.nova-micro', 'amazon.nova-pro', 'aws'):
        ai_response = library.api.aws.bedrock_ask.query_aws_bedrock(query, model, temperature=temperature,
                                                                    max_token_count=max_token_count, top_p=top_p)

        # if isinstance(response, bytes):
        #     response = response.decode('utf-8')

        # ai_response.response_text = response
        return ai_response
    elif model in ["Bielik-11B-v2.3-Instruct"]:
        return sherlock_get_completion(query, model=model)
    elif model in ['gemini-2.0-flash-lite-001']:
        return google_vertexai.connect_to_google_llm_with_role(query, model)

    else:
        raise Exception(f"ERROR: Unknown model {model}")
