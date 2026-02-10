import json
from pprint import pprint
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()


@logger.inject_lambda_context

def lambda_handler(event, context):

    # pprint(event)
    logger.info(event)
    body = json.loads(event['body'])
    logger.info(body)
    logger.info(body['ip'])

    ip_address = event['requestContext']['identity']['sourceIp']
    api_key_id = event['requestContext']['identity']['apiKeyId']
    security_group_id = 'sg-0929bfcae31074fb8'
    logger.append_keys(ip_address=ip_address, api_key_id=api_key_id,security_group_id=security_group_id)
    
    
    ec2_client = boto3.client('ec2')

    try:
        response = ec2_client.describe_security_groups(GroupIds=[security_group_id])
        security_group = response['SecurityGroups'][0]
        
        ip_permission_exists = False
        
        for permission in security_group['IpPermissions']:
            if (permission['IpProtocol'] == 'tcp' and
                permission['FromPort'] == 3389 and
                permission['ToPort'] == 3389):
                for ip_range in permission['IpRanges']:
                    if ip_range['CidrIp'] == f'{ip_address}/32':
                        ip_permission_exists = True
                        break
            if ip_permission_exists:
                break
        if not ip_permission_exists:
            ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3389,
                        'ToPort': 3389,
                        'IpRanges': [{'CidrIp': f'{ip_address}/32'}]
                    }
                ]
            )
            logger.info(f"Successfully added {ip_address} (apiKeyId: {api_key_id}) to the security group {security_group_id}")
            return {
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Credentials': True,
                },
                'statusCode': 200,
                'body': json.dumps('Your access has been granted!')
            }
        else:
            logger.info(f"The rule for {ip_address} already exists in the security group {security_group_id}")
            return {
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Credentials': True,
                },
                'statusCode': 200,
                'body': json.dumps('Your access has already been granted!')
            }

    except Exception as e:
        logger.info(f"Error processing the request for {ip_address} (apiKeyId: {api_key_id}): {str(e)}")
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 500,
            'body': json.dumps('There is error on server site, please inform administrator')
        }
