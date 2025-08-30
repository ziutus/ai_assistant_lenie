from pprint import pprint

from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

print(">>CloudFerro Sherlock<<")
# Ustaw klucz API oraz podstawowe URL
clientCloudFerro = OpenAI(
    api_key=os.environ['CLOUDFERRO_SHERLOCK_KEY'],
    base_url="https://api-sherlock.cloudferro.com/openai/v1"
)

# Check available models
models = clientCloudFerro.models.list()

for model in models.data:
    pprint(model)
