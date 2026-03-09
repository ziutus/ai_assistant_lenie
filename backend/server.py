import os
from pprint import pprint

from flask import Flask, Response, request, abort
from flask_cors import CORS
import logging
import uuid

from library.config_loader import load_config
from library.db.engine import get_scoped_session
from library.db.models import WebDocument
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.text_transcript import chapters_text_to_list
from library.website.website_download_context import download_raw_html, webpage_raw_parse, webpage_text_clean
from library.models.webpage_parse_result import WebPageParseResult
from library.website.website_paid import website_is_paid
from library.text_functions import split_text_for_embedding
from library.ai_intent_parser import parse_intent

logging.basicConfig(level=logging.INFO)

cfg = load_config()

env_data = cfg.require("ENV_DATA")

APP_VERSION = "0.3.13.0"
BUILD_TIME = "2026.01.23 04:04"

logging.info(f"APP VERSION={APP_VERSION} (build time:{BUILD_TIME})")
logging.info("ENV_DATA: %s", env_data)

llm_provider = cfg.require("LLM_PROVIDER")

if llm_provider == "openai":
    openai_organization = cfg.require("OPENAI_ORGANIZATION")
    openai_api_key = cfg.require("OPENAI_API_KEY")

llm_simple_jobs_model = cfg.require("AI_MODEL_SUMMARY")

backend_type = cfg.require("BACKEND_TYPE", "postgresql")

if backend_type == "postgresql":
    cfg.require("POSTGRESQL_HOST")
    cfg.require("POSTGRESQL_DATABASE")
    cfg.require("POSTGRESQL_USER")
    cfg.require("POSTGRESQL_PASSWORD")
    cfg.require("POSTGRESQL_PORT")

    logging.debug("Using PostgreSQL database")
else:
    logging.error("ERROR: Unknown backend type: >%s<", backend_type)
    exit(1)

embedding_model = cfg.require("EMBEDDING_MODEL")

logging.info("Using embedding model: %s", embedding_model)

port = cfg.require("PORT")

def check_auth_header():
    """
  Function to validate 'x-api-key' in request headers
  """
    api_key = request.headers.get('x-api-key')
    if api_key is None:
        abort(400, 'x-api-key header is missing')
    if api_key != cfg.require("STALKER_API_KEY"):
        abort(400, 'x-api-key header is wrong')


logging.info("Starting flask application")
app = Flask(__name__)
logging.info("Flask - enabling CORS for all routes")
CORS(app)  # This will enable CORS for all routes


@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up scoped session at end of Flask request."""
    get_scoped_session().remove()


@app.before_request
def before_request_func():
    exempt_paths = ['/healthz', '/startup', '/readiness', '/liveness', '/version']
    if request.path not in exempt_paths and request.method != 'OPTIONS':
        check_auth_header()

@app.route('/', methods=['GET', 'OPTIONS'])
def root():
    """
    Główna trasa aplikacji - endpoint informacyjny
    """
    response = {
        "status": "success",
        "message": "Stalker Web Documents API",
        "app_version": APP_VERSION,
        "app_build_time": BUILD_TIME,
        "encoding": "utf8"
    }
    return response, 200


@app.route('/url_add', methods=['POST', 'OPTIONS'])
def url_add():
    """
    Dodaje nowy URL do systemu z zapisywaniem treści HTML do S3 i danych do bazy
    Funkcjonalność analogiczna do lambda_handler w lambda_function.py
    """

    if request.method == 'OPTIONS':
        response = {
            'status': 'OK',
            'message': 'CORS preflight'
        }
        return response, 200

    # Pobranie zmiennych środowiskowych
    bucket_name = cfg.get("AWS_S3_WEBSITE_CONTENT")

    use_aws_s3 = True
    if bucket_name is None:
        use_aws_s3 = False

    logging.info(f"Using AWS S3: {use_aws_s3}")

    try:
        # Pobranie danych z requestu
        url_data = request.get_json()

        if not url_data:
            return {
                'status': 'error',
                'message': 'No JSON data provided'
            }, 400

        # Logowanie danych (z ograniczeniem dla długich treści)
        url_data_print = url_data.copy()
        if 'text' in url_data_print:
            url_data_print['text'] = url_data_print['text'][:50]
        if 'html' in url_data_print:
            url_data_print['html'] = url_data_print['html'][:50]

        logging.info('Data received by API', extra={"body": url_data_print})

        # Pobranie parametrów
        target_url = url_data.get("url")
        url_type = url_data.get("type")
        note = url_data.get("note", "default_note")
        text = url_data.get("text", "")
        html = url_data.get("html", "")
        title = url_data.get("title", "")
        language = url_data.get("language", "")
        paywall = url_data.get("paywall", False)
        source = url_data.get("source", "own")
        ai_summary = url_data.get("ai_summary", False)
        chapter_list = url_data.get("chapter_list", False)

        if not target_url or not url_type:
            error_message = "Missing required parameter(s): 'url' or 'type'"
            logging.error(error_message)
            return {
                'status': 'error',
                'message': error_message
            }, 400

        s3_uuid = None

        if use_aws_s3:
            # Inicjalizacja klienta S3
            # Import biblioteki AWS (analogicznie do lambda)
            import boto3
            s3 = boto3.client('s3')


        if url_type == 'webpage':
            # Generowanie UUID i zapis do S3
            uid = str(uuid.uuid4())
            s3_uuid = uid

            # Zapis tekstu do S3
            if text:
                file_name = f"{uid}.txt"

                if use_aws_s3:
                    try:
                        s3.put_object(Bucket=bucket_name, Key=file_name, Body=text)
                        logging.info(f"Successfully uploaded {file_name} to {bucket_name}")
                    except Exception as e:
                        error_message = f"Failed to upload {file_name} to {bucket_name}: {str(e)}"
                        logging.error(error_message)
                        return {
                            'status': 'error',
                            'message': error_message
                        }, 500
                else:
                    # Zapis lokalny
                    try:
                        os.makedirs('/app/data', exist_ok=True)
                        local_file_path = f"/app/data/{file_name}"
                        with open(local_file_path, 'w', encoding='utf-8') as f:
                            f.write(text)
                        logging.info(f"Successfully saved {file_name} to /app/data/")
                    except Exception as e:
                        error_message = f"Failed to save {file_name} to /app/data/: {str(e)}"
                        logging.error(error_message)
                        return {
                            'status': 'error',
                            'message': error_message
                        }, 500



            # Zapis HTML do S3
            if html:
                file_name = f"{uid}.html"

                if use_aws_s3:
                    try:
                        s3.put_object(Bucket=bucket_name, Key=file_name, Body=html)
                        logging.info(f"Successfully uploaded {file_name} to {bucket_name}")
                    except Exception as e:
                        error_message = f"Failed to upload {file_name} to {bucket_name}: {str(e)}"
                        logging.error(error_message)
                        return {
                            'status': 'error',
                            'message': error_message
                        }, 500
                else:
                    # Zapis lokalny
                    try:
                        os.makedirs('/app/data', exist_ok=True)
                        local_file_path = f"/app/data/{file_name}"
                        with open(local_file_path, 'w', encoding='utf-8') as f:
                            f.write(html)
                        logging.info(f"Successfully saved {file_name} to /app/data/")
                    except Exception as e:
                        error_message = f"Failed to save {file_name} to /app/data/: {str(e)}"
                        logging.error(error_message)
                        return {
                            'status': 'error',
                            'message': error_message
                        }, 500

            else:
                logging.info("Missing HTML part!")

        # Zapis do bazy danych
        try:
            session = get_scoped_session()
            doc = WebDocument(url=target_url)
            doc.set_document_type(url_type)
            doc.note = note
            doc.title = title
            doc.language = language
            doc.paywall = paywall
            doc.source = source
            doc.ai_summary_needed = ai_summary
            # Skip ai_correction_needed — column does NOT exist in DB or ORM model
            doc.chapter_list = chapter_list
            doc.s3_uuid = s3_uuid

            # Ustawienie stanu dokumentu
            doc.set_document_state("URL_ADDED")

            session.add(doc)
            session.commit()

            logging.info(f"Successfully saved document to database with ID: {doc.id}")

            return {
                'status': 'success',
                'message': f'Successfully saved document with ID: {doc.id}',
                'document_id': doc.id
            }, 200

        except Exception as e:
            session.rollback()
            error_message = f"Failed to save to database: {str(e)}"
            logging.error(error_message)
            return {
                'status': 'error',
                'message': error_message
            }, 500

    except Exception as e:
        error_message = f"Unexpected error: {str(e)}"
        logging.error(error_message)
        return {
            'status': 'error',
            'message': error_message
        }, 500


@app.route('/website_list', methods=['GET'])
def website_list():
    logging.debug("Getting list of websites")
    logging.debug(request.form)

    document_type = request.args.get('type', 'ALL')
    document_state = request.args.get('document_state', 'ALL')
    search_in_documents = request.args.get('search_in_document', '')
    logging.debug(document_type)

    session = get_scoped_session()
    repo = WebsitesDBPostgreSQL(session)
    websites_list = repo.get_list(document_type=document_type, document_state=document_state, search_in_documents=search_in_documents)
    websites_list_count = repo.get_list(document_type=document_type, document_state=document_state, search_in_documents=search_in_documents, count=True)
    logging.debug("website count: %s", websites_list_count)

    response = {
        "status": "success",
        "message": "Dane odczytane pomyślnie.",
        "encoding": "utf8",
        "websites": websites_list,
        "all_results_count": websites_list_count
    }

    return response, 200


@app.route('/website_count', methods=['GET'])
def website_count():
    """Return document counts grouped by type in a single query."""
    logging.debug("Getting document counts by type")
    session = get_scoped_session()
    repo = WebsitesDBPostgreSQL(session)
    counts = repo.get_count_by_type()
    return {"status": "success", "counts": counts}, 200


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

    session = get_scoped_session()
    doc = WebDocument.get_by_id(session, int(link_id), reach=True)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404
    return doc.dict(), 200


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

    session = get_scoped_session()
    repo = WebsitesDBPostgreSQL(session)
    next_data = repo.get_next_to_correct(link_id)
    if next_data == -1:
        response = {
            "status": "success",
            "next_id": -1,
            "next_type": "",
        }
        return response, 200
    next_id = next_data[0]
    next_type = next_data[1]
    logging.info(next_id)
    response = {
        "status": "success",
        "next_id": next_id,
        "next_type": next_type,
    }

    return response, 200

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
    embedds = embedding.get_embedding(model=cfg.require("EMBEDDING_MODEL"), text=text)

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
    embedds = embedding.get_embedding(model=cfg.require("EMBEDDING_MODEL"), text=text)

    if embedds.status != "success" or len(embedds.embedding) == 0:
        return {"status": embedds.status, "message": "Error during getting embedding for text", "encoding": "utf8", "text": text,
                "websites": []}, 500

    # Legacy instance — get_similar() not yet migrated to ORM (Epic 28)
    legacy_repo = WebsitesDBPostgreSQL()  # No session → psycopg2 mode
    websites_list = legacy_repo.get_similar(embedds.embedding, cfg.require("EMBEDDING_MODEL"), limit=limit)
    legacy_repo.close()

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


@app.route('/website_text_remove_not_needed', methods=['POST'])
def website_text_remove_not_needed():
    if request.form:
        logging.debug("Using form")

    logging.debug("website_text_remove_not_needed")
    logging.debug(request.form)

    text = request.form.get('text')
    url = request.form.get('url')

    # debug_needed = False
    # if debug_needed:
    #     with open('debug.txt', 'w', encoding='utf-8') as debug_file:
    #         debug_file.write(f"text: {text}\n")
    #         debug_file.write(f"url: {url}\n")
    #         logging.info("Debug data written into file debug.txt")

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

    link_id = request.args.get('id')
    logging.debug(link_id)

    if not link_id:
        logging.debug("Missing data. Make sure you provide 'id'")
        return {"status": "error",
                "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400

    session = get_scoped_session()
    doc = WebDocument.get_by_id(session, int(link_id))

    if doc is None:
        response = {
            "status": "success",
            "message": "Page doesn't exist in database",
            "encoding": "utf8",
        }
        return response, 200

    try:
        session.delete(doc)
        session.commit()
        response = {
            "status": "success",
            "message": "Page has been deleted from database",
            "encoding": "utf8",
        }
        return response, 200
    except Exception as e:
        session.rollback()
        logging.error(e)
        return {"status": "error", "message": str(e)}, 500


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
    session = get_scoped_session()

    if link_id:
        doc = WebDocument.get_by_id(session, int(link_id))
    else:
        doc = WebDocument.get_by_url(session, url)

    if doc is None:
        doc = WebDocument(url=url)
        session.add(doc)

    document_state = request.form.get('document_state')
    if document_state is not None:
        doc.set_document_state(document_state)

    for attr in ('text', 'title', 'language', 'tags', 'summary', 'source', 'author', 'note'):
        value = request.form.get(attr)
        if value is not None:
            setattr(doc, attr, value)

    try:
        document_type = request.form.get('document_type')
        if document_type is not None:
            doc.set_document_type(document_type)
    except Exception as e:
        logging.error(f"Wrong document type: {e}")
        return {"status": "error", "message": f"Wrong document type: {request.form.get('document_type')}."}, 500

    doc.analyze()

    try:
        session.commit()
        return {"status": "success", "message": f"Dane strony {doc.id} zaktualizowane pomyślnie."}, 200
    except Exception as e:
        session.rollback()
        logging.error(e)
        logging.debug(f"Error while saving new webpage: {e}")
        return {"status": "error", "message": str(e)}, 500


@app.route('/ai_parse_intent', methods=['POST'])
def ai_parse_intent():
    """Parse natural language text into a structured command intent using LLM."""
    intent_enabled = cfg.get("INTENT_PARSER_ENABLED", "false").lower() == "true"
    if not intent_enabled:
        return {"status": "error", "message": "Intent parser is disabled"}, 400

    if request.json:
        text = request.json.get("text", "")
    else:
        return {"status": "error", "message": "JSON body with 'text' field required"}, 400

    if not text or not text.strip():
        return {"status": "error", "message": "Empty text provided"}, 400

    logging.debug("Intent parse request received")

    result = parse_intent(text)
    return {
        "status": "success",
        "command": result["command"],
        "args": result["args"],
        "confidence": result["confidence"],
    }, 200


@app.route('/healthz', methods=['GET'])
def healthz():
    return {"status": "OK", "message": "Server is running"}, 200


# metrics in Prometheus format
@app.route('/metrics', methods=['GET'])
def kubernetes_metrics():
    metrics = "# HELP lenie_app_info Application information\n"
    metrics += "# TYPE lenie_app_info gauge\n"
    metrics += f'lenie_app_info{{version="{APP_VERSION}"}} 1\n'
    return Response(metrics, mimetype='text/plain; charset=utf-8')


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
    if cfg.require("USE_SSL", "false") == "true":
        logging.debug("Using SSL")
        app.run(debug=cfg.require("DEBUG", "false").lower() == "true", host='0.0.0.0', port=port, ssl_context='adhoc')
    else:
        logging.debug("Using HTTP")
        app.run(debug=cfg.require("DEBUG", "false").lower() == "true", port=port, host='0.0.0.0')
