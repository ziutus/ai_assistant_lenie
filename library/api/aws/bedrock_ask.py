import boto3
import json
import os
import botocore.exceptions
from aws_xray_sdk.core import xray_recorder, patch_all

patch_all()


def query_aws_bedrock(query: str) -> str:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))

    client_bedrock = session.client(service_name='bedrock-runtime', region_name=os.getenv("AWS_REGION"))

    prompt_data = f"""Command: Answer to query {query}"""

    body = json.dumps({
        "inputText": prompt_data,
        "textGenerationConfig": {
            "maxTokenCount": 4096,
            "stopSequences": [],
            "temperature": 0,
            "topP": 0.9
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

    return answer
