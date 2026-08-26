import os

from google.cloud import compute_v1

INSTANCE_NAME = os.environ.get("INSTANCE_NAME")
ZONE = os.environ.get("ZONE")
PROJECT_ID = os.environ.get("PROJECT_ID")

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Credentials": "true",
}


def vpn_relay_control(request):
    if not (INSTANCE_NAME and ZONE and PROJECT_ID):
        return ("INSTANCE_NAME, ZONE or PROJECT_ID environment variable is not set", 400, HEADERS)

    body = request.get_json(silent=True) or {}
    action = (request.args.get("action") or body.get("action") or "").lower()

    client = compute_v1.InstancesClient()

    try:
        if action == "start":
            client.start(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)
            result = f"Successfully started instance {INSTANCE_NAME}"
        elif action == "stop":
            client.stop(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)
            result = f"Successfully stopped instance {INSTANCE_NAME}"
        elif action == "status":
            instance = client.get(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)
            result = instance.status
        else:
            return (f"Unknown action: {action}", 400, HEADERS)

        print(f"{action} for {INSTANCE_NAME}: {result}")
        return (result, 200, HEADERS)
    except Exception as e:
        print(f"Error during {action} for {INSTANCE_NAME}: {e}")
        return (f"Error during {action} for {INSTANCE_NAME}: {e}", 500, HEADERS)
