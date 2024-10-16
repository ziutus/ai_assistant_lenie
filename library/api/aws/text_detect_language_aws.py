import os

import boto3


def detect_text_language_aws(text: str) -> str:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))
    client = session.client('comprehend',region_name=os.getenv("AWS_REGION"))

    response = client.detect_dominant_language(Text=text)

    language_code = response['Languages'][0]['LanguageCode']

    return language_code
