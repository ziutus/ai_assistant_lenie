import boto3
import os

from library.text_functions import get_hash


def cache_get_language(entry_id, provider) -> str | None:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    response = dynamodb.get_item(
        TableName='lenie_cache_language',
        Key={
            'hash': {
                'S': entry_id,
            }
            ,
            'provider': {
                'S': provider,
            },
        },
    )

    if 'Item' in response:
        return response['Item']
    else:
        return None


def cache_write_language_check(text_input: str, translation: str, provider: str) -> None:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    dynamodb.put_item(
        Item={
            'hash': {'S': get_hash(text_input)},
            'provider': {'S': provider},
            'query': {'S': text_input},
            'response': {'S': translation}
        },
        ReturnConsumedCapacity='TOTAL',
        TableName='lenie_cache_language',
    )
