import boto3
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import os
from pprint import pprint


def s3_file_exist(s3_bucket: str, filename: str) -> bool:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))
    s3 = session.client(service_name='s3', region_name=os.getenv("AWS_REGION"))
    try:
        s3.get_object_attributes(Bucket=s3_bucket, Key=filename, ObjectAttributes=['ObjectSize'])
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print("This filename doesn't exist on S3")
            return False
        else:
            print("Unexpected error: ", e)
            raise Exception("An error occurred")
    except NoCredentialsError:
        print("S3 could not authenticate with AWS.")
        raise Exception("Authentication credentials were not provided.")
    except Exception as e:
        print("An error occurred: ", str(e))
        raise Exception("An error occurred")
