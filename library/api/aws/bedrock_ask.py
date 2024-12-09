from pprint import pprint

import boto3
import json
import os
import botocore.exceptions
from aws_xray_sdk.core import xray_recorder, patch_all
from library.ai_response import AiResponse

patch_all()


def query_aws_bedrock(query: str, model: str, temperature: float = 0.7, max_token_count: int = 4096,
                      top_p: float = 0.9) -> AiResponse:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))

    client_bedrock = session.client(service_name='bedrock-runtime', region_name=os.getenv("AWS_REGION"))
    ai_response = AiResponse(query=query, model=model)
    ai_response.model = model
    ai_response.temperature = temperature
    ai_response.max_token_count = max_token_count
    ai_response.top_p = top_p

    prompt_data = f"""Command: Answer to query {query}"""

    if model == 'amazon.titan-tg1-large' or model == 'aws':

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

        with xray_recorder.in_subsegment('translate single test'):

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

    elif model == 'amazon.nova-micro':

        # Ustawienia regionu AWS i identyfikator modelu
        AWS_REGION = "us-east-1"
        MODEL_ID = "amazon.nova-micro-v1:0"

        # Inicjalizacja klienta Bedrock
        bedrock_runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)

        # Definiowanie wiadomości do modelu
        messages = [
            {"role": "user", "content": [{"text": query}]}
        ]

        # Wywołanie modelu
        response = bedrock_runtime.converse(
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

