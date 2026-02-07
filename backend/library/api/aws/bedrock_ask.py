# from pprint import pprint

import boto3
import json
import os
import botocore.exceptions
from library.models.ai_response import AiResponse


def query_aws_bedrock(query: str, model: str, temperature: float = 0.7, max_token_count: int = 4096,
                      top_p: float = 0.9) -> AiResponse:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))

    client_bedrock = session.client(service_name='bedrock-runtime', region_name=os.getenv("AWS_REGION"))

    ai_response = AiResponse(query=query, model=model)
    ai_response.model = model
    ai_response.temperature = temperature
    ai_response.max_token_count = max_token_count
    ai_response.top_p = top_p

    if model == 'amazon.titan-tg1-large' or model == 'aws':
        prompt_data = f"""Command: Answer to query {query}"""

        body = json.dumps({
            "inputText": prompt_data,
            "textGenerationConfig": {
                "maxTokenCount": max_token_count,
                "stopSequences": [],
                "temperature": temperature,
                "topP": top_p
            }
        })

        model_id = 'amazon.titan-tg1-large'  # change this to use a different version from the model provider
        accept = 'application/json'
        content_type = 'application/json'
        output_text = "\n"

        try:

            response = client_bedrock.invoke_model(body=body, modelId=model_id, accept=accept, contentType=content_type)
            response_body = json.loads(response.get('body').read())
            output_text = response_body.get('results')[0].get('outputText')

        except botocore.exceptions.ClientError as error:

            if error.response['Error']['Code'] == 'AccessDeniedException':
                print(f"\x1b[41m{error.response['Error']['Message']}\
                        \nTo troubeshoot this issue please refer to the following resources.\
                         \nhttps://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html\
                         \nhttps://docs.aws.amazon.com/bedrock/latest/userguide/security-iam.html\x1b[0m\n")

            else:
                raise Exception(error)

        if output_text.find('\n') != -1:
            answer = output_text[output_text.index('\n') + 1:]
        else:
            answer = output_text

        ai_response.response_text = answer
        ai_response.output_tokens = int(response['ResponseMetadata']['HTTPHeaders']['x-amzn-bedrock-output-token-count'])
        ai_response.input_tokens = int(response['ResponseMetadata']['HTTPHeaders']['x-amzn-bedrock-input-token-count'])
        ai_response.total_tokens = ai_response.output_tokens + ai_response.input_tokens

        return ai_response

    elif model in ['amazon.nova-micro', 'amazon.nova-pro']:

        if model == 'amazon.nova-micro':
            MODEL_ID = "amazon.nova-micro-v1:0"
        elif model == 'amazon.nova-pro':
            MODEL_ID = "amazon.nova-pro-v1:0"
        else:
            raise Exception("Unknown model")

        messages = [
            {"role": "user", "content": [{"text": query}]}
        ]

        response = client_bedrock.converse(
            modelId=MODEL_ID,
            messages=messages,
            inferenceConfig={"temperature": temperature}
        )

        response_text = response["output"]["message"]["content"][0]["text"]

        ai_response.response_text = response_text
        ai_response.total_tokens = int(response['usage']['totalTokens'])
        ai_response.input_tokens = int(response['usage']['inputTokens'])
        ai_response.output_tokens = int(response['usage']['outputTokens'])

        return ai_response

    else:
        raise Exception("Unknown model")


def aws_bedrock_describe_image(base64_image, model_id="anthropic.claude-3-haiku-20240307-v1:0", max_tokens=1000,
                               media_type="image/png", question="What's in this image?") -> AiResponse:
    if media_type not in ["image/png", "image/jpeg"]:
        raise ValueError("Invalid media type. Supported types: image/png, image/jpeg")

    ai_response = AiResponse(query=question, model=model_id)
    ai_response.model = model_id
    ai_response.max_token_count = max_tokens

    # Inicjalizacja klienta Bedrock
    session = boto3.Session()
    client_bedrock = session.client(
        service_name='bedrock-runtime',
        region_name=os.getenv("AWS_REGION", "us-east-1")  # Ustaw domyślny region na `us-east-1` jeśli nie podany
    )

    # Przygotowanie payloadu
    payload = {
        "modelId": model_id,
        "contentType": "application/json",
        "accept": "application/json",
        "body": json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": question
                        }
                    ]
                }
            ]
        })
    }

    response = client_bedrock.invoke_model(
        modelId=payload["modelId"],
        contentType=payload["contentType"],
        accept=payload["accept"],
        body=payload["body"]
    )

    response_body = json.loads(response['body'].read().decode('utf-8'))

    ai_response.input_tokens = int(response_body['usage']['input_tokens'])
    ai_response.output_tokens = int(response_body['usage']['output_tokens'])
    ai_response.total_tokens = ai_response.input_tokens + ai_response.output_tokens

    ai_response.response_text = response_body['content'][0]['text']

    return ai_response
