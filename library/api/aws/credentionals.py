

def validate_credentials(aws_boto_session):

    try:
        sts_client = aws_boto_session.client('sts')
        response = sts_client.get_caller_identity()
        print(response)
        return True
    except Exception as e:
        print("Error: Invalid Access Key")
        print(str(e))
        exit(1)
