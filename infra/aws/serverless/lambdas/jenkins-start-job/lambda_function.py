import requests
from requests.auth import HTTPBasicAuth
import os
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# Configuration and constants will be loaded dynamically inside lambda_handler



def lambda_handler(event, context):
    logger.info(event)

    # Load environment variables
    jenkins_url = os.getenv("JENKINS_URL")
    username = os.getenv("JENKINS_USER")
    password = os.getenv("JENKINS_PASSWORD")
    job_name = os.getenv("JENKINS_JOB_NAME")
    branche_name = event.get("branch", "main")

    if not all([jenkins_url, username, password]):
        logger.error("Missing one or more required environment variables.")
        raise RuntimeError("Missing required environment variables.")

    # Parameters
    parameters = {
        "INSTANCE_ID": os.getenv("INSTANCE_ID"),
        "AWS_REGION": os.getenv("AWS_REGION"),
        "BRANCH_NAME": branche_name
    }

    # Create session
    session = requests.Session()
    session.auth = HTTPBasicAuth(username, password)

    # Get Crumb Token
    crumb_url = f"{jenkins_url}/crumbIssuer/api/json"
    try:
        crumb_response = session.get(crumb_url, verify=False)
        crumb_response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch crumb token: {e}")
        raise RuntimeError("Could not fetch crumb token.")

    crumb_data = crumb_response.json()
    crumb_field = crumb_data["crumbRequestField"]
    crumb = crumb_data["crumb"]

    # Update headers with Crumb
    session.headers.update({crumb_field: crumb})

    # Build endpoint and trigger job
    build_url = f"{jenkins_url}/job/{job_name}/buildWithParameters"
    try:
        response = session.post(build_url, params=parameters, verify=False)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to trigger Jenkins job: {e}")
        return {
            "statusCode": response.status_code if "response" in locals() else 500,
            "body": "Jenkins job trigger failed."
        }

    # Response handling
    if response.status_code == 201:
        logger.info("Successfully triggered Jenkins job.")
        return {
            "statusCode": 201,
            "body": "Jenkins job triggered successfully."
        }
    else:
        logger.error(f"Unexpected status code: {response.status_code}")
        return {
            "statusCode": response.status_code,
            "body": response.text
        }
