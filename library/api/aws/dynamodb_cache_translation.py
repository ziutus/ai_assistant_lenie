import os

import boto3
from aws_xray_sdk.core import xray_recorder, patch_all
from library.text_functions import get_hash

patch_all()


def cache_get_translation(entry_id: str, provider: str) -> str | None:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    with xray_recorder.in_subsegment('dynamoDB_get_translation') as subsegment:

        try:
            response = dynamodb.get_item(
                Key={
                    'hash': {
                        'S': entry_id,
                    },
                    'provider': {
                        'S': provider,
                    }
                },
                TableName='lenie_cache_translation',
            )

            subsegment.put_metadata('response', response)

            if 'Item' in response:
                return response['Item']
            else:
                return None

        finally:
            # End the segment
            xray_recorder.end_segment()


def cache_write_translation(query: str, response: str, provider: str) -> None:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    with xray_recorder.in_subsegment('dynamoDB_put_translation') as subsegment:
        item = {
            'hash': {'S': get_hash(query)},
            'provider': {'S': provider},
            'query': {'S': query},
            'response': {'S': response}
        }

        subsegment.put_metadata('Item', item)

        dynamodb.put_item(
            Item=item,
            ReturnConsumedCapacity='TOTAL',
            TableName='lenie_cache_translation',
        )
