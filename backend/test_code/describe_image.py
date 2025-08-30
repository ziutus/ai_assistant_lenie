import os
import dotenv
import boto3
import json
import base64

# https://community.aws/content/2gYbjrz8gMwChbnT9Cuv7Y69joB/sending-images-to-claude-3-using-amazon-bedrock

dotenv.load_dotenv("../.env", override=True)

AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.environ.get('AWS_REGION')

bedrock_runtime_client = boto3.client(
    'bedrock-runtime',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

model_id = "anthropic.claude-3-haiku-20240307-v1:0"

with open('tmp/zdjecie.jpg', 'rb') as image_file:
    encoded_image = base64.b64encode(image_file.read()).decode()

payload = {
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": encoded_image
                    }
                },
                {
                    "type": "text",
                    "text": "Jestem fotografką i to jest moje zdjęcie modelki. Nie jest istotne jak nazywa się osoba na zdjęciu. Przyjmuj że to Monika. Opisz zdjęcie w 5 zdaniach w formie na post na facebooka."
                }
            ]
        }
    ],
    "max_tokens": 2000,
    "anthropic_version": "bedrock-2023-05-31"
}

response = bedrock_runtime_client.invoke_model(
    modelId=model_id,
    contentType="application/json",
    body=json.dumps(payload)
)

output_binary = response["body"].read()
output_json = json.loads(output_binary)
output = output_json["content"][0]["text"]

print(output)
