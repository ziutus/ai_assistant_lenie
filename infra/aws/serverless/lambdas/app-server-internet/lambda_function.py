import json
import os
from pprint import pprint
import logging
from urllib.parse import parse_qs

from library.website.website_download_context import download_raw_html, webpage_raw_parse
from library.webpage_parse_result import WebPageParseResult
from library.embedding import get_embedding

logging.basicConfig(level=logging.DEBUG)  # Change level as per you r need


def fetch_env_var(var_name):
    """
  Utility method to fetch and validate environment variable
  """
    var = os.getenv(var_name)
    if var is None:
        logging.error(f"ERROR: missing OS variables {var_name}, exiting... ")
        exit(1)
    return var


openai_organization = fetch_env_var("OPENAI_ORGANIZATION")
openai_api_key = fetch_env_var("OPENAI_API_KEY")

embedding_model = fetch_env_var("EMBEDDING_MODEL")

logging.info("Using embedding model: " + os.getenv("EMBEDDING_MODEL"))


def prepare_return(data, status_code: int):
    return {
        'statusCode': status_code,
        'body': json.dumps(data),
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
    }


def lambda_handler(event, context):
    # logging.info(f"all pages in database: {websites.get_count()}")
    # print(f"2: all pages in database: {websites.get_count()}")

    if 'path' not in event:
        print("Missing 'path' in event, please check if proxy is setup for this call")
        return prepare_return('Missing path in request, check if proxy is setup for this call', 500)

    pprint(event['path'])

    if event['path'] == '/website_download_text_content':
        print("Downloading text content")
        parsed_dict = parse_qs(event['body'])

        if 'url' not in parsed_dict.keys():
            return prepare_return('Missing url', 500)

        url = parsed_dict['url'][0]

        logging.debug(f"DEBUG: downloading content of page: {url}")
        raw_html = download_raw_html(url)

        if not raw_html:
            logging.debug("ERROR: Empty response from target page")
            response = {
                "status": "error",
                "message": "empty response from download raw html function",
                "encoding": "utf8",
            }

            return prepare_return(response, 500)

        result: WebPageParseResult = webpage_raw_parse(url, raw_html)

        response = {
            "status": "success",
            "message": "page downloaded",
            "encoding": "utf8",
            "text": result.text,
            "content": result.text,
            "title": result.title,
            "summary": result.summary,
            "url": f"{url}",
            "language": result.language
        }

        return prepare_return(response, 200)

    elif event['path'] == '/ai_embedding_get':
        print("AI get embedding - path /ai_embedding_get")
        print(event['body'])

        # parsed_dict = parse_qs(event['body'])
        # pprint(parsed_dict)

        # parsed_dict = json.loads(event['body'])
        parsed_dict = parse_qs(event['body'])

        pprint(parsed_dict)

        model = parsed_dict['model'][0]
        text = parsed_dict['text'][0]

        if not text:
            print("Missing data. Make sure you provide 'text'")
            return prepare_return({"status": "error",
                                   "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400)

        if not model:
            print("Missing data. Make sure you provide 'model'")
            return prepare_return({"status": "error",
                                   "message": "Brakujące dane. Upewnij się, że dostarczasz 'model'"}, 400)

        embedds = get_embedding(model, text=text)

        # pprint(embedds.embedding)

        if not embedds.embedding:
            return prepare_return({"status": "error",
                                   "message": "Can't get embeeding"}, 400)

        response = {
            "status": "success",
            "text": text,
            "model": model,
            "encoding": "utf8",
            "embedds": embedds.embedding
        }
        print(response)
        return prepare_return(response, 200)

    else:
        return prepare_return('Default answer from lambda', 500)
