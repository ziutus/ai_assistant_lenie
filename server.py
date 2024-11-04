import os
from pprint import pprint

from dotenv import load_dotenv
from flask import Flask, request, abort
from flask_cors import CORS
import logging

import library.ai
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.text_transcript import chapters_text_to_list
from library.translate import text_translate
from library.website.website_download_context import download_raw_html, webpage_raw_parse, WebPageParseResult, \
    webpage_text_clean
from library.website.website_paid import website_is_paid
from library.text_functions import split_text_for_embedding

logging.basicConfig(level=logging.INFO)  # Change level as per your need
load_dotenv()


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
env_data = fetch_env_var("ENV_DATA")

llm_simple_jobs_model = fetch_env_var("AI_MODEL_SUMMARY")

APP_VERSION = "0.2.11.0"
BUILD_TIME = "2024.09.50 09:50"

logging.info(f"APP VERSION={APP_VERSION} (build time:{BUILD_TIME})")
logging.info("ENV_DATA: " + os.getenv("ENV_DATA"))

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

port = fetch_env_var("PORT")

logging.info(f"all pages in database: {websites.get_count()}")


def check_auth_header():
    """
  Function to validate 'x-api-key' in request headers
  """
    api_key = request.headers.get('x-api-key')
    if api_key is None:
        abort(400, 'x-api-key header is missing')
    if api_key != fetch_env_var("STALKER_API_KEY"):
        abort(400, 'x-api-key header is wrong')


logging.info("Starting flask application")
app = Flask(__name__)
logging.info("Flask - enabling CORS for all routes")
CORS(app)  # This will enable CORS for all routes


@app.before_request
def before_request_func():
    exempt_paths = ['/startup', '/readiness', '/liveness', '/version']
    if request.path not in exempt_paths and request.method != 'OPTIONS':
        check_auth_header()


@app.route('/website_list', methods=['GET'])
def website_list():
    logging.debug("Getting list of websites")
    logging.debug(request.form)

    document_type = request.args.get('type', 'ALL')
    document_state = request.args.get('document_state', 'ALL')
    search_in_documents = request.args.get('search_in_document', '')
    logging.debug(document_type)

    websites_list = websites.get_list(document_type=document_type, document_state=document_state, search_in_documents=search_in_documents)
    websites_list_count = websites.get_list(document_type=document_type, document_state=document_state, search_in_documents=search_in_documents, count=True)
    # pprint_debug(websites_list)
    print(f"website count: {websites_list_count}")

    response = {
        "status": "success",
        "message": "Dane odczytane pomyślnie.",
        "encoding": "utf8",
        "websites": websites_list,
        "all_results_count": websites_list_count
    }

    return response, 200


@app.route('/website_is_paid', methods=['POST'])
def website_check_is_paid():
    logging.debug("Checking if website is paid")

    if request.form:
        logging.debug("Using form")
        logging.debug(request.form)
        url = request.form.get('url')
    elif request.json:
        logging.debug("Using json")
        logging.debug(request.json)
        url = request.json['url']
    else:
        logging.debug("Using args")
        logging.debug(request.args)
        url = request.args.get('url')

    logging.debug(url)

    if not url:
        logging.debug("Missing data. Make sure you provide 'url'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'url'"}, 400

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

    return response, 200


@app.route('/website_get', methods=['GET'])
def website_get_by_id():
    logging.debug("Getting website by id")
    logging.debug(request.args)

    link_id = request.args.get('id')
    logging.debug(link_id)

    if not link_id:
        logging.debug("Missing data. Make sure you provide 'id'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400

    web_document = StalkerWebDocumentDB(document_id=int(link_id), reach=True)
    return web_document.dict(), 200


@app.route('/website_get_next_to_correct', methods=['GET'])
def website_get_next_to_correct():
    logging.debug("Getting website by id, new style")
    logging.debug(request.args)

    link_id = request.args.get('id')
    logging.debug(link_id)

    if not link_id:
        logging.debug("Missing data. Make sure you provide 'id'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400

    next_data = websites.get_next_to_correct(link_id)
    pprint(next_data)
    next_id = next_data[0]
    next_type = next_data[1]
    logging.info(next_id)
    response = {
        "status": "success",
        "next_id": next_id,
        "next_type": next_type,
    }

    return response, 200


@app.route('/translate', methods=['POST'])
def translate():
    logging.debug("Translating")
    logging.debug(request.form)

    text = request.form.get('text')
    target_language = request.form.get('target_language')
    source_language = request.form.get('source_language')

    logging.debug(text)
    logging.debug(target_language)
    logging.debug(source_language)

    if not text or not target_language:
        logging.debug("Missing data. Make sure you provide 'text' and 'target_language'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'text' i 'target_language'"}, 400

    result = text_translate(text=text, target_language=target_language, source_language=source_language)
    # logging.debug(result.text)
    if result.status == "success":
        return {"status": "success", "message": result.translated_text}, 200
    else:
        logging.error(result.error_message)
        return {"status": "error", "message": result.error_message}, 500


@app.route('/ai_get_embedding', methods=['POST'])
def ai_get_embedding():
    if request.form:
        logging.debug("Using form")
        logging.debug(request.form)
        text = request.form.get('search')
    elif request.json:
        logging.debug("Using json")
        logging.debug(request.json)
        text = request.json['search']
    else:
        logging.debug("Using args")
        logging.debug(request.args)
        text = request.args.get('search')

    import library.embedding as embedding
    embedds = embedding.get_embedding(model=os.getenv("EMBEDDING_MODEL"), text=text)

    return {"status": "success", "message": "Dane odczytane pomyślnie.", "encoding": "utf8", "text": text,
            "embedding": embedds}, 200


@app.route('/website_similar', methods=['POST'])
def search_similar():
    if request.form:
        print("Searching using form")
        pprint(request.form)
        logging.debug("Using form")
        logging.debug(request.form)
        text = request.form.get('search')
        limit = request.form.get('limit')
    elif request.json:
        print("Searching using json")
        pprint(request.json)
        logging.debug("Using json")
        logging.debug(request.json)
        text = request.json['search']
        limit = request.json['limit']
    else:
        print("Searching using args")
        pprint(request.args)
        logging.debug("Using args")
        logging.debug(request.args)
        text = request.args.get('search')
        limit = request.args.get('limit')

    logging.info(f"searching embedding for {text}")

    import library.embedding as embedding
    embedds = embedding.get_embedding(model=os.getenv("EMBEDDING_MODEL"), text=text)

    if embedds.status != "success" or len(embedds.embedding) == 0:
        return {"status": embedds.status, "message": "Error during getting embedding for text", "encoding": "utf8", "text": text,
                "websites": []}, 500

    websites_list = websites.get_similar(embedds.embedding, os.getenv("EMBEDDING_MODEL"), limit=limit)

    return {"status": "success", "message": "Dane odczytane pomyślnie.", "encoding": "utf8", "text": text,
            "websites": websites_list}, 200


@app.route('/website_download_text_content', methods=['POST'])
def website_download_text_content():
    logging.debug("Downloading text content")
    if request.form:
        logging.debug(request.form)
        url = request.form.get('url')
    elif request.json:
        logging.debug(request.json)
        url = request.json['url']
    else:
        logging.debug("Missing data. Make sure you provide 'url'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'url'"}, 400

    logging.debug(url)
    if not url:
        logging.debug("Missing data. Make sure you provide 'url'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'url'"}, 400

    logging.debug(f"DEBUG: downloading content of page: {url}")
    raw_html = download_raw_html(url)
    if not raw_html:
        logging.debug("ERROR: Empty response from target page")
        response = {
            "status": "error",
            "message": "empty response from download raw html function",
            "encoding": "utf8",
        }

        return response, 500

    result: WebPageParseResult = webpage_raw_parse(url, raw_html)

    logging.debug(f"Zawartość: {result.text[:500]}")  # Wydrukowanie tylko pierwszych 500 znaków zawartości

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

    return response, 200

    # else:
    #     print_debug(f"Nie udało się pobrać strony. Kod statusu: {response.status_code}")
    #
    #     response = {
    #         "status": "failed",
    #         "message": "page downloading failed",
    #         "encoding": "utf8",
    #         "url": f"{url}"
    #     }
    #
    #     return response, 500


@app.route('/ai_ask', methods=['POST'])
def ai_ask():
    logging.debug("Correcting text using AI")
    logging.debug(request.form)

    text = request.form.get('text')
    query = request.form.get('query')
    model = request.form.get('model')

    if not query:
        # logging.info("Using default query to correct website as nothing is comming from fronted")
        # query = f"Dla treści poniżej popraw błędy interpunkcyjne. Zwróć tylko poprawioną treść.   ---Treść--- {text}"
        logging.debug("Missing data. Make sure you provide 'query'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'query'"}, 400

    if not text:
        logging.debug("Missing data. Make sure you provide 'text'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400

    if not model:
        logging.debug("Missing data. Make sure you provide 'model'")
        return {"status": "error",
                "message": "Missing data, please provide 'model' to decide which LLM model should be used"}, 400

    query = query.replace("{text}", text)

    logging.debug(f"query: {query}")

    try:
        llm_answer = library.ai.ai_ask(query=query, model=model)
        logging.debug(llm_answer)

        response = {
            "status": "success",
            "text": llm_answer.response_text,
            "model": llm_answer.model,
            "encoding": "utf8",
            "message": "Text corrected"
        }
        logging.debug(response)
        return response, 200

    except Exception as e:
        logging.error(f"An error occurred: {e}")

        response = {
            "status": "failed",
            "text": text,
            "encoding": "utf8",
            "message": str(e)
        }

        logging.debug(response)
        return response, 500


@app.route('/website_text_remove_not_needed', methods=['POST'])
def website_text_remove_not_needed():
    if request.form:
        logging.debug("Using form")

    logging.debug("website_text_remove_not_needed")
    logging.debug(request.form)

    text = request.form.get('text')
    url = request.form.get('url')

    debug_needed = False
    if debug_needed:
        with open('debug.txt', 'w', encoding='utf-8') as debug_file:
            debug_file.write(f"text: {text}\n")
            debug_file.write(f"url: {url}\n")
            logging.info("Debug data written into file debug.txt")

    if not text:
        logging.debug("Missing data. Make sure you provide 'text'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400

    if not url:
        logging.debug("Missing data. Make sure you provide 'url'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400

    response = {
        "status": "success",
        "text": webpage_text_clean(url, text),
        "encoding": "utf8",
        "message": "Text cleaned"
    }
    logging.debug(response)
    return response, 200


@app.route('/website_split_for_embedding', methods=['POST'])
def website_split_for_embedding():
    if request.form:
        logging.debug("Using form")

    logging.debug("Split for Embedding")
    logging.debug(request.form)

    text = request.form.get('text')
    pprint(text)

    chapters_list_text = request.form.get('chapter_list')

    chapters_list = chapters_text_to_list(chapters_list_text)
    chapter_list_simple = []

    for chapter in chapters_list:
        chapter_list_simple.append(chapter['title'])

    if not text:
        logging.debug("Missing data. Make sure you provide 'text'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400

    response = {
        "status": "success",
        "text": split_text_for_embedding(text, chapter_list_simple),
        "encoding": "utf8",
        "message": "Text corrected"
    }
    logging.debug(response)
    return response, 200


@app.route('/website_delete', methods=['GET'])
def website_delete():
    logging.debug("Deleting website")
    logging.debug(request.form)

    link_id = int(request.args.get('id'))
    logging.debug(link_id)

    if not link_id:
        logging.debug("Missing data. Make sure you provide 'id'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400

    web_document = StalkerWebDocumentDB(document_id=link_id)

    if not web_document.id:
        response = {
            "status": "success",
            "message": "Page doesn't exist in database",
            "encoding": "utf8",
        }
        return response, 200

    web_document.delete()
    response = {
        "status": "success",
        "message": "Page has been deleted from database",
        "encoding": "utf8",
    }
    return response, 200


@app.route('/website_save', methods=['POST'])
def website_save():
    logging.debug("Saving website (adding or updating)")
    logging.debug(request.form)

    url = request.form.get('url')
    logging.debug(url)
    if not url:
        logging.debug("Missing data. Make sure you provide 'url'")
        return {"status": "error", "message": "Missing data. Make sure you provide 'url'"}, 400

    link_id = request.form.get('id')

    if link_id:
        web_document = StalkerWebDocumentDB(document_id=int(link_id))
    else:
        web_document = StalkerWebDocumentDB(url=url)

    web_document.set_document_state(request.form.get('document_state'))

    web_document.text = request.form.get('text')
    web_document.text_english = request.form.get('text_english')

    web_document.title = request.form.get('title')
    web_document.language = request.form.get('language')
    web_document.tags = request.form.get('tags')
    web_document.summary = request.form.get('summary')
    web_document.source = request.form.get('source')
    web_document.author = request.form.get('author')
    web_document.note = request.form.get('note')
    web_document.analyze()

    try:
        web_document.set_document_type(request.form.get('document_type'))
    except Exception as e:
        print(f"An error occurred: {e}")
        return {"status": "error", "message": f"Wrong document type: {request.form.get('document_type')}."}, 500

    try:
        web_document.save()
        return {"status": "success", "message": f"Dane strony {web_document.id} zaktualizowane pomyślnie."}, 200
    except Exception as e:
        logging.error(e)
        logging.debug(f"Error while saving new webpage: {e}")
        return {"status": "error", "message": str(e)}, 500


@app.route('/healthz', methods=['GET'])
def healthz():
    return {"status": "OK", "message": "Server is running"}, 200


# metrics in Prometheus format
@app.route('/metrics', methods=['GET'])
def kubernetes_metrics():
    pass


@app.route('/startup', methods=['GET'])
def kubernetes_startup():
    # https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
    return {"status": "OK", "message": "Server initialization ended"}, 200


@app.route('/readiness', methods=['GET'])
def kubernetes_readiness():
    # https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
    return {"status": "OK", "message": "Server is ready to provide data to user"}, 200


@app.route('/liveness', methods=['GET'])
def kubernetes_liveness():
    # https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
    return {"status": "OK", "message": "Server is ready and will not be restarted"}, 200


@app.route('/version', methods=['GET'])
def app_version():
    response = {
        "status": "success",
        "app_version": APP_VERSION,
        "app_build_time": BUILD_TIME,
        "encoding": "utf8"
    }
    logging.debug(response)
    return response, 200


if __name__ == '__main__':
    if os.getenv("USE_SSL") == "true":
        logging.debug("Using SSL")
        app.run(debug=True, host='0.0.0.0', port=os.getenv("PORT"), ssl_context='adhoc')
    else:
        logging.debug("Using HTTP")
        app.run(debug=True, port=os.getenv("PORT"), host='0.0.0.0')
