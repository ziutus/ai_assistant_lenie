import os

import boto3

from library.text_functions import get_hash


def cache_get_query(entry_id: str, provider: str) -> None:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    response = dynamodb.get_item(
        Key={
            'hash': {'S': entry_id},
            'provider': {'S': provider},
        },
        TableName='lenie_cache_ai_query',
    )

    if 'Item' in response:
        return response['Item']
    else:
        return None


def cache_write_query(query: str, response: str, provider: str) -> None:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    dynamodb.put_item(
        Item={
            'hash': {'S': get_hash(query)},
            'provider': {'S': provider},
            'query': {'S': query},
            'response': {'S': response}
        },
        ReturnConsumedCapacity='TOTAL',
        TableName='lenie_cache_ai_query',
    )
