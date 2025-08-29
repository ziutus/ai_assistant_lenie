import json
from pprint import pprint
import boto3
from botocore.exceptions import ClientError
import logging

logging.info(
    "extra parameters example",
    extra={"a": "b", "b": [3]},
)

bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")


def lambda_handler(event, context):
    logging.info("Lambda function started", extra={"request_id": context.aws_request_id}, )

    if "body" not in event:
        logging.info("Body is empty in event", extra={"event": event})
        return {
            'statusCode': 500,
            'body': "body is empty"
        }

    abc = json.loads(event["body"])
    logging.info("Received request body", extra={"body": abc})

    if "instruction" in abc:
        logging.info("Instruction found in request", extra={"instruction": abc["instruction"]})

        model_id = "anthropic.claude-3-haiku-20240307-v1:0"

        # Define the prompt for the model.
        prompt = f"""
        Jesteś operatorem dronu i latasz po mapie zdefiniowanej poniżej.
        Dostajesz informacje gdzie aktualnie na mapie się znajdujesz i jak lecisz.
        Jeżeli informacja o punkcie startu nie jest podana, używasz domyślnego punktu startowego. 

        Mapa jest wielkości 4x4. 
        Domyslny punkt startowy znajduje się w lewym górnym rogu i jest to pozycja (1,1)
        jaskinia znajduje się w prawym dolnym rogu,  i jest to pozycja (4,4)
        Punkt skrajny prawy górny to (4,1) i jest to dom,
        puntk skrajny lewy dolny to (1,4) i są to góry,

        Nie można wychodzić poza planszę, gdy się poruszasz.

        Pole (1,1) to start,
        Pole (2,1) to trawa,
        Pole (3,1) to drzewa,
        Pole (4,1) to dom,

        pole (1,2) to trawa,
        pole (2,2) to wiatrak,
        pole (3,2) to trawa,
        pole (4,2) to trawa,

        pole (1,3) to trawa,
        pole (2,3) to trawa,
        pole (3,3) to wgórza,
        pole (4,3) to las      

        pole (1,4) to góry,
        pole (2,4) go góry,
        pole (3,4) to samochód,
        pole (4,4) to jaskinia,

        Instrukcja: {abc["instruction"]}

        odpowiedz w postaci json
        Json ma postać:
        {{
            "answer": "opis pola koncowego",
            "instruction": "{abc["instruction"]}",
            "thinking", "opis jak znaleziono odpowiedz, podaj lokalizacje pól i liczbę pól przez które przechodzisz"
        }}

        """

        logging.info("Generated prompt for Bedrock",
                     extra={"model_id": model_id, "prompt_length": len(prompt), "prompt": prompt})

        # Format the request payload using the model's native structure.
        native_request = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "temperature": 0.5,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        }

        # Convert the native request to JSON.
        request = json.dumps(native_request)

        try:
            # Invoke the model with the request.
            response = bedrock_client.invoke_model(modelId=model_id, body=request)
            logging.info("Received response from Bedrock")

        except (ClientError, Exception) as e:
            log_event("bedrock_error", "Error invoking Bedrock", error=error_message, model_id=model_id)

            return {
                'statusCode': 500,
                'body': str(e)
            }

        # Decode the response body.
        model_response = json.loads(response["body"].read())

        # Extract and print the response text.
        response_text = model_response["content"][0]["text"]
        response_json = json.loads(response_text)

        answer = {
            "description": response_json["answer"]
        }

        logging.info("model_prompt_response",
                     extra={"prompt": prompt, "response": response_json, "response_length": len(response_text)})

        # TODO implement
        return {
            'statusCode': 200,
            'body': json.dumps(answer)
        }

    answer = {
        "description": "Error Error Error"
    }

    # TODO implement
    return {
        'statusCode': 200,
        'body': json.dumps(answer)
    }
