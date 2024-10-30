import os
import boto3
from aws_xray_sdk.core import xray_recorder, patch_all

patch_all()


def detect_text_language_aws(text: str) -> str:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))
    client = session.client('comprehend',region_name=os.getenv("AWS_REGION"))

    with xray_recorder.in_subsegment('detect_dominant_language'):
        response = client.detect_dominant_language(Text=text)

        language_code = response['Languages'][0]['LanguageCode']

        return language_code
