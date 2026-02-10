import json
import boto3
import logging
from pprint import pprint

def lambda_handler(event, context):
    if event.get("body"):
        body = json.loads(event["body"])
        print("Parsed body:", json.dumps(body, indent=2))
        if body["ref"]:
            branch = body["ref"].replace("refs/heads/", "")
            print(f"setup branch to {branch}")
    else:
        body = {}
        branch = "main"
        print(f"setup branch to default: 'main'")
        print("Body is missing in the request.")

    stepfunctions_client = boto3.client('stepfunctions')
    state_machine_arn = "arn:aws:states:us-east-1:008971653395:stateMachine:jenkins-start-run-job"

    input_data = {"branch": branch, "job_name": "lenie_server"}

    response = stepfunctions_client.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(input_data)
    )

    pprint(response)

    return {
        'statusCode': 200,
        'body': json.dumps('The step function has been run')
    }
