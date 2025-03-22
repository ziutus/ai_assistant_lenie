import json
import os
from pprint import pprint
import logging
from urllib.parse import parse_qs

import library.ai
from library.translate import text_translate
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
llm_simple_jobs_model = fetch_env_var("AI_MODEL_SUMMARY")
backend_type = fetch_env_var("BACKEND_TYPE")

# if os.getenv("BACKEND_TYPE") == "postgresql":
#     if not os.getenv("POSTGRESQL_HOST") or not os.getenv("POSTGRESQL_DATABASE") or not os.getenv("POSTGRESQL_USER") \
#             or not os.getenv("POSTGRESQL_PASSWORD") or not os.getenv("POSTGRESQL_PORT"):
#         logging.error("ERROR: missing configuration data for PostgreSQL, exiting...")
#         exit(1)
#
#     logging.debug("Using PostgreSQL database")
#     websites = WebsitesDBPostgreSQL()
# else:
#     logging.error("ERROR: Unknown backend type: >" + os.getenv("BACKEND_TYPE") + "<")
#     exit(1)

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

    if event['path'] == '/translate':

        logging.debug("Translating")
        logging.debug(event['body'])

        parsed_dict = parse_qs(event['body'])

        text = parsed_dict['text'][0]
        target_language = parsed_dict['target_language'][0]
        source_language = parsed_dict['source_language'][0]

        logging.debug(text)
        logging.debug(target_language)
        logging.debug(source_language)

        if not text or not target_language:
            logging.debug("Missing data. Make sure you provide 'text' and 'target_language'")
            return prepare_return({"status": "error",
                                   "message": "Brakujące dane. Upewnij się, że dostarczasz 'text' i 'target_language'"},
                                  400)

        result_t = text_translate(text=text, target_language=target_language, source_language=source_language)
        # logging.debug(result.text)
        if result_t.status == "success":
            return prepare_return({"status": "success", "message": result_t.translated_text}, 200)
        else:
            logging.error(result_t.error_message)
            return prepare_return({"status": "error", "message": result_t.error_message}, 500)

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

    if event['path'] == '/ai_embedding_get':
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

    if event['path'] == '/ai_ask':
        print("ask AI - path /ai_ask")
        print(event['body'])

        parsed_dict = parse_qs(event['body'])

        text = parsed_dict['text'][0]
        query = parsed_dict['query'][0]
        model = parsed_dict['model'][0]

        if not text:
            print("Missing data. Make sure you provide 'text'")
            return prepare_return({"status": "error",
                                   "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400)

        if not query:
            print("Missing data. Make sure you provide 'query'")
            return prepare_return({"status": "error",
                                   "message": "Brakujące dane. Upewnij się, że dostarczasz 'query'"}, 400)

        if not model:
            print("Missing data. Make sure you provide 'model'")
            return prepare_return({"status": "error",
                                   "message": "Brakujące dane. Upewnij się, że dostarczasz 'model'"}, 400)

        query = query.replace("{text}", text)
        logging.debug(f"query: {query}")

        try:
            llm_answer = library.ai.ai_ask(query=query, model=llm_simple_jobs_model)
            print(llm_answer)

            response = {
                "status": "success",
                "text": llm_answer.response_text,
                "model": llm_answer.model,
                "encoding": "utf8",
                "message": "Text corrected"
            }
            print(response)
            return prepare_return(response, 200)

        except Exception as e:
            print(f"An error occurred: {e}")

            response = {
                "status": "failed",
                "text": text,
                "encoding": "utf8",
                "message": str(e)
            }

            print(response)
            return prepare_return(response, 500)

    return prepare_return('Default answer from lambda', 500)
