import os
import boto3


def cache_get_webpage_raw_html(entry_id: str) -> str | False:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    response = dynamodb.get_item(
        Key={
            'url': {
                'S': entry_id,
            }
        },
        TableName='lenie_webpage_raw_html',
    )

    if 'Item' in response:
        return response['Item']['raw_html']['S']
    else:
        return False


def cache_write_webpage_raw_html(url: str, raw_html: str) -> None:
    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    dynamodb = boto_session.client('dynamodb')

    dynamodb.put_item(
        Item={
            'url': {'S': url},
            'raw_html': {'S': raw_html},
        },
        ReturnConsumedCapacity='TOTAL',
        TableName='lenie_webpage_raw_html',
    )
