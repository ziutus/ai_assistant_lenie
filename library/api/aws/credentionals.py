from aws_xray_sdk.core import xray_recorder


def validate_credentials(aws_boto_session):

    with xray_recorder.in_subsegment('translate single test') as subsegment:
        try:
            sts_client = aws_boto_session.client('sts')
            response = sts_client.get_caller_identity()
            print(response)
            return True
        except Exception as e:
            subsegment.add_exception(e)
            print("Error: Invalid Access Key")
            print(str(e))
            exit(1)
