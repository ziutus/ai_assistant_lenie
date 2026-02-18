import json
import logging
import os
from pprint import pprint
from urllib.parse import parse_qs

from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.text_functions import split_text_for_embedding
from library.text_transcript import chapters_text_to_list
from library.website.website_paid import website_is_paid

logging.basicConfig(level=logging.DEBUG)  # Change level as per your need


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

if os.getenv("BACKEND_TYPE") == "postgresql":
    if not os.getenv("POSTGRESQL_HOST") or not os.getenv("POSTGRESQL_DATABASE") or not os.getenv("POSTGRESQL_USER") \
            or not os.getenv("POSTGRESQL_PASSWORD") or not os.getenv("POSTGRESQL_PORT"):
        logging.error("ERROR: missing configuration data for PostgreSQL, exiting...")
        exit(1)

    logging.debug("Using PostgreSQL database")
    websites = WebsitesDBPostgreSQL()
else:
    logging.error("ERROR: Unknown backend type: >" + os.getenv("BACKEND_TYPE") + "<")
    exit(1)

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


def lambda_handler(event, _):
    # logging.info(f"all pages in database: {websites.get_count()}")
    # print(f"2: all pages in database: {websites.get_count()}")

    if 'path' in event:
        pprint(event['path'])

    if 'path' not in event:
        print("Missing 'path' in event, please check if proxy is setup for this call")
        return prepare_return('Missing path in request, check if proxy is setup for this call', 500)

    if event['path'] == '/website_list':
        query_params = event.get('queryStringParameters', {})
        pprint(query_params)
        document_state = query_params.get('document_state', 'ALL')
        document_type = query_params.get('type', 'ALL')
        search_in_documents = query_params.get('search_in_document', '')

        websites_list = websites.get_list(document_type=document_type, document_state=document_state,
                                          search_in_documents=search_in_documents)

        response = {
            "status": "success",
            "message": "Dane odczytane pomyślnie.",
            "encoding": "utf8",
            "websites": websites_list
        }

        return prepare_return(response, 200)

    if event['path'] == '/website_is_paid':
        print("Endpoint: Website_is_paid")
        parsed_dict = parse_qs(event['body'])

        if 'url' not in parsed_dict.keys():
            return prepare_return('Missing url', 500)

        url = parsed_dict['url'][0]

        print(f"Url to check: {url}")

        is_paid = website_is_paid(url)
        logging.debug(f"is_paid: {is_paid}")

        message = "Page is paid, can't download content" if is_paid else "Page is not paid, can download content"

        response = {
            "status": "success",
            "message": message,
            "encoding": "utf8",
            "is_paid": is_paid,
            "url": url
        }

        logging.debug(response)

        return prepare_return(response, 200)

    if event['path'] == '/website_get':
        if 'id' not in event['queryStringParameters']:
            return prepare_return('Missing ID parameter', 500)

        document_id = event['queryStringParameters']['id']
        web_document = StalkerWebDocumentDB(document_id=int(document_id), reach=True)

        return prepare_return(web_document.dict(), 200)

    if event['path'] == '/website_get_next_to_correct':
        if 'id' not in event['queryStringParameters']:
            return prepare_return('Missing ID parameter', 500)

        query_params = event.get('queryStringParameters', {})
        pprint(query_params)
        # pprint(event['queryStringParameters'])
        document_id = event['queryStringParameters']['id']
        document_type = query_params.get('document_type', 'ALL')
        document_state = query_params.get('document_state', 'ALL')

        next_data = websites.get_next_to_correct(document_id, document_type, document_state)
        pprint(next_data)

        if next_data == -1:
            next_data = websites.get_next_to_correct(-1, document_type, document_state)

        next_id = next_data[0]
        next_type = next_data[1]
        logging.info(next_id)
        response = {
            "status": "success",
            "next_id": next_id,
            "next_type": next_type,
        }

        return prepare_return(response, 200)

    if event['path'] == '/website_similar':
        # pprint(event['body'])

        parsed_dict = parse_qs(event['body'])

        if parsed_dict:
            parsed_dict_tmp = parsed_dict
            if "embedds" in parsed_dict_tmp:
                parsed_dict_tmp = "truncted but extist"
            pprint(parsed_dict_tmp)

        embedds = '[' + ','.join(parsed_dict['embedds[]']) + ']'
        model = parsed_dict['model'][0]
        if 'limit' in parsed_dict:
            limit = int(parsed_dict['limit'][0])
        else:
            limit = 5

        pprint(limit)

        # embedds = embedding.get_embedding(model=os.getenv("EMBEDDING_MODEL"), text=text)

        # print(type(embedds))

        websites_list = websites.get_similar(embedds, model, limit)

        return prepare_return({"status": "success", "message": "Dane odczytane pomyślnie.", "encoding": "utf8",
                               "websites": websites_list}, 200)

    # if event['path'] == '/website_download_text_content' - in internet version - with access to others AWS services

    # if event['path'] == '/website_correct_using_ai' - in internet version - with access to others AWS services

    if event['path'] == '/website_split_for_embedding':
        logging.debug("website_split_for_embedding")
        logging.debug(event['body'])

        parsed_dict = parse_qs(event['body'])

        text = parsed_dict['text'][0]

        if not text:
            logging.debug("Missing data. Make sure you provide 'text'")
            return prepare_return({"status": "error",
                                   "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400)

        chapter_list_simple = []

        if 'chapter_list' in parsed_dict:
            chapters_list_text = parsed_dict['chapter_list'][0]

            chapters_list = chapters_text_to_list(chapters_list_text)

            for chapter in chapters_list:
                chapter_list_simple.append(chapter['title'])

        response = {
            "status": "success",
            "text": split_text_for_embedding(text, chapter_list_simple),
            "encoding": "utf8",
            "message": "Text corrected"
        }
        pprint(response)
        return prepare_return(response, 200)

    if event['path'] == '/website_delete':
        print("Deleting document")

        if 'id' not in event['queryStringParameters']:
            return prepare_return('Missing document ID parameter', 500)

        document_id = event['queryStringParameters']['id']
        print(document_id)

        web_document = StalkerWebDocumentDB(document_id=document_id)

        if not web_document.id:
            response = {
                "status": "success",
                "message": "Page doesn't exist in database",
                "encoding": "utf8",
            }
            return prepare_return(response, 200)

        web_document.delete()
        response = {
            "status": "success",
            "message": "Page has been deleted from database",
            "encoding": "utf8",
        }
        return prepare_return(response, 200)

    if event['path'] == '/website_save':
        parsed_dict = parse_qs(event['body'])
        pprint(type(parsed_dict))

        # pprint(parsed_dict.keys())

        if 'url' not in parsed_dict.keys():
            return prepare_return('Missing url', 500)

        if 'id' in parsed_dict.keys():
            web_document = StalkerWebDocumentDB(document_id=int(parsed_dict['id'][0]))
        else:
            web_document = StalkerWebDocumentDB(url=parsed_dict['url'][0])

        if 'document_type' in parsed_dict.keys():
            try:
                web_document.set_document_type(parsed_dict['document_type'][0])
            except Exception as e:
                print(f"An error occurred: {e}")
                return {"status": "error", "message": f"Wrong document type {parsed_dict['document_type'][0]}."}, 500

        if 'document_state' in parsed_dict.keys():
            web_document.set_document_state(parsed_dict['document_state'][0])

        if 'text' in parsed_dict.keys():
            web_document.text = parsed_dict['text'][0]

        if 'text_english' in parsed_dict.keys():
            web_document.text_english = parsed_dict['text_english'][0]

        if 'title' in parsed_dict.keys():
            web_document.title = parsed_dict['title'][0]

        if 'language' in parsed_dict.keys():
            web_document.language = parsed_dict['language'][0]

        if 'summary' in parsed_dict.keys():
            web_document.summary = parsed_dict['summary'][0]

        if 'tags' in parsed_dict.keys():
            web_document.tags = parsed_dict['tags'][0]

        if 'source' in parsed_dict.keys():
            web_document.source = parsed_dict['source'][0]

        if 'author' in parsed_dict.keys():
            web_document.author = parsed_dict['author'][0]

        if 'note' in parsed_dict.keys():
            web_document.note = parsed_dict['note'][0]

        web_document.analyze()

        try:
            web_document.save()
            return prepare_return(
                {"status": "success", "message": f"Dane strony {web_document.id} zaktualizowane pomyślnie."}, 200)
        except Exception as e:
            logging.error(e)
            logging.debug(f"Error while saving new webpage: {e}")
            return prepare_return({"status": "error", "message": str(e)}, 500)

    return prepare_return('Default answer from lambda', 500)
