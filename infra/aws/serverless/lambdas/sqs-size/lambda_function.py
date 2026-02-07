import boto3
import json
import os


def generate_response(status_code, body):
    return {
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
        },
        'statusCode': status_code,
        'body': json.dumps(body)
    }


def lambda_handler(event, context):
    region_name = os.getenv('AWS_REGION', 'us-east-1')

    ssm_client = boto3.client('ssm', region_name=region_name)

    # Pobieranie wartości parametru z SSM
    try:
        parameter = ssm_client.get_parameter(Name='/lenie/dev/sqs_queue/new_links', WithDecryption=True)
        queue_url = parameter['Parameter']['Value']
    except Exception as e:
        return generate_response(500, f'Błąd podczas pobierania parametru z SSM: {str(e)}')

    # Tworzenie klienta SQS
    sqs_client = boto3.client('sqs', region_name=region_name)

    # Pobieranie atrybutów kolejki
    try:
        response = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        # Pobieranie liczby wiadomości w kolejce
        number_of_messages = int(response['Attributes']['ApproximateNumberOfMessages'])
    except Exception as e:
        return generate_response(500, f'Błąd podczas pobierania atrybutów z SQS: {str(e)}')

    return generate_response(200, number_of_messages)
