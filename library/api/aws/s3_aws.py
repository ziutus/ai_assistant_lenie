import os

import boto3
from aws_xray_sdk.core import xray_recorder, patch_all
from botocore.exceptions import ClientError, NoCredentialsError

patch_all()


def s3_file_exist(s3_bucket: str, filename: str) -> bool:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))
    s3 = session.client(service_name='s3', region_name=os.getenv("AWS_REGION"))
    with xray_recorder.in_subsegment('s3_file_exist') as subsegment:
        try:
            s3.get_object_attributes(Bucket=s3_bucket, Key=filename, ObjectAttributes=['ObjectSize'])
            return True
        except ClientError as e:
            subsegment.add_exception(e)
            if e.response['Error']['Code'] == 'NoSuchKey':
                print("This filename doesn't exist on S3")
                return False
            else:
                print("Unexpected error: ", e)
                raise Exception("An error occurred")
        except NoCredentialsError as e:
            subsegment.add_exception(e)
            print("S3 could not authenticate with AWS.")
            raise Exception("Authentication credentials were not provided.")
        except Exception as e:
            subsegment.add_exception(e)
            print("An error occurred: ", str(e))
            raise Exception("An error occurred")

def s3_take_file(s3_bucket: str, object_key: str, local_filename: str) -> bool:
    session = boto3.Session(region_name=os.getenv("AWS_REGION"))
    s3 = session.client(service_name='s3', region_name=os.getenv("AWS_REGION"))
    try:
        s3.download_file(s3_bucket, object_key, local_filename)
        return True
    except Exception as e:
        print("An error occurred: ", str(e))
        return False
