import boto3
from botocore.exceptions import ClientError
import json
import os
from library.models.embedding_result import EmbeddingResult

# https://www.philschmid.de/amazon-titan-embeddings
# https://www.youtube.com/watch?v=UsbAuGV4rkw


def get_embedding(text: str) -> EmbeddingResult:
    boto_session = boto3.Session(region_name=os.getenv("AWS_REGION"))
    bedrock = boto_session.client("bedrock-runtime")

    accept = 'application/json'
    content_type = 'application/json'
    model_id = "amazon.titan-embed-text-v1"

    result = EmbeddingResult(text=text, model_id=model_id)

    body = json.dumps({
        "inputText": text
    })

    try:
        response = bedrock.invoke_model(body=body, modelId=model_id, accept=accept, contentType=content_type)
        response_body = json.loads(response.get('body').read())

        result.status = "success"
        result.embedding = response_body['embedding']
        result.input_text_token_count = response_body['inputTextTokenCount']

        return result

    except ClientError as e:
        result.status = "error"
        result.error_message = e.__str__()

        return result


def get_embedding2(text: str) -> EmbeddingResult:
    # https://github.com/aws-samples/amazon-bedrock-samples/blob/main/multimodal/Titan/embeddings/v2/Titan-V2-Embeddings.ipynb
    boto_session = boto3.Session(region_name=os.getenv("AWS_REGION"))
    bedrock = boto_session.client("bedrock-runtime")

    accept = 'application/json'
    content_type = 'application/json'
    model_id = "amazon.titan-embed-text-v2:0"

    body = json.dumps({
        "inputText": text
    })

    result = EmbeddingResult(text=text, model_id=model_id)

    try:
        response = bedrock.invoke_model(body=body, modelId=model_id, accept=accept, contentType=content_type)
        response_body = json.loads(response.get('body').read())

        result.status = "success"
        result.embedding = response_body['embedding']
        result.input_text_token_count = response_body['inputTextTokenCount']

        return result

    except ClientError as e:
        result.status = "error"
        result.error_message = e.__str__()

        return result
