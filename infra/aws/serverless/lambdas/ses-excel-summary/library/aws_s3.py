import logging
import sys

import boto3
from botocore.exceptions import ClientError


def save_to_s3(content, file_name, bucket_name):
    s3_client = boto3.client('s3')
    try:
        s3_client.put_object(Body=content, Bucket=bucket_name, Key=file_name)
        logging.info(f"File {file_name} successfully saved to S3 bucket {bucket_name}")
    except ClientError as error:
        logging.error(f"Could not save file to S3: {error}")
        sys.exit(1)
