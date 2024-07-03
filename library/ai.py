import library.api.openai.openai_my
from library.api.aws.text_detect_language_aws import detect_text_language_aws
import library.api.aws.bedrock_ask
from library.stalker_cache import cache_get, cache_write
from library.translate import text_translate
from library.text_detect_language import text_language_detect

import logging


class AiResponse:
    def __init__(self, query, model = None):
        self.cached = False
        self.query = query
        self.model = model
        self.response_text = None


def ai_model_need_translation_to_english(model: str) -> bool:
    if model in ['amazon.titan-tg1-large']:
        return True
    elif model in ["gpt-4", "gpt-3.5-turbo"]:
        return True
    else:
        raise Exception(f"DEBUG: Error, no model info for text {model}")


def ai_ask(query: str, model: str) -> AiResponse:
    ai_response= AiResponse(query=query, model=model)

    if model in ["gpt-3.5-turbo", "gpt-3.5-turbo-16k"]:
        if len(str) < 8000:
            model = "gpt-3.5-turbo"
        elif len(str) < 16000:
            model = "gpt-3.5-turbo-16k"
        else:
            raise Exception("To long text for gpt-3.5 models")
        ai_response.model = model

        response = library.api.openai.openai_my.OpenAIClient.get_completion(query, model)

        if isinstance(response, bytes):
            response = response.decode('utf-8')

        ai_response.response_text = response
        return ai_response
    if model in ["gpt-4", "gpt-4o"]:
        response = library.api.openai.openai_my.OpenAIClient.get_completion(query, model)

        if isinstance(response, bytes):
            response = response.decode('utf-8')

        ai_response.response_text = response
        return ai_response
    elif model == 'amazon.titan-tg1-large' or model == 'aws':
        response = library.api.aws.bedrock_ask.query_aws_bedrock(query)

        if isinstance(response, bytes):
            response = response.decode('utf-8')

        ai_response.response_text = response
        return ai_response
    else:
        raise Exception(f"ERROR: Unknown model {model}")
