import json
import os

import boto3

import library.api.aws.bedrock_ask
import library.api.openai.openai_my
from library.ai_response import AiResponse


def ai_model_need_translation_to_english(model: str) -> bool:
    if model in ['amazon.titan-tg1-large']:
        return True
    elif model in ["gpt-4", "gpt-3.5-turbo"]:
        return True
    else:
        raise Exception(f"DEBUG: Error, no model info for text {model}")


def ai_ask(query: str, model: str, temperature: float = 0.7, max_token_count: int = 4096,
                      top_p: float = 0.9) -> AiResponse:

    if model in ["gpt-3.5-turbo", "gpt-3.5-turbo-16k"]:
        if len(str) < 8000:
            model = "gpt-3.5-turbo"
        elif len(str) < 16000:
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
    elif model == 'amazon.titan-tg1-large' or model =='amazon.nova-micro' or model == "amazon.nova-pro" or model == 'aws':
        ai_response = library.api.aws.bedrock_ask.query_aws_bedrock(query, model, temperature =temperature,
                                                                 max_token_count =max_token_count,top_p = top_p)

        # if isinstance(response, bytes):
        #     response = response.decode('utf-8')

        # ai_response.response_text = response
        return ai_response
    else:
        raise Exception(f"ERROR: Unknown model {model}")


def ai_describe_image(base64_image, model_id="anthropic.claude-3-haiku-20240307-v1:0", max_tokens = 1000, media_type = "image/png", question="What's in this image?"):
    if media_type not in ["image/png", "image/jpeg"]:
        raise ValueError("Invalid media type. Supported types: image/png, image/jpeg")

    if model_id == "anthropic.claude-3-haiku-20240307-v1:0":
        response_text = library.api.aws.bedrock_ask.aws_bedrock_describe_image(base64_image, model_id, max_tokens, media_type, question)
    else:
        raise Exception("Unknown model")

    return response_text
