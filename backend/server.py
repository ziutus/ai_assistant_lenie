from flask import Flask, Response, g, request, abort, jsonify
from flask_cors import CORS
import logging

from library.config_loader import load_config
from library.db.engine import get_scoped_session
from library.db.models import TranscriptionLog, WebDocument
from library.document_service import DocumentService
from library.search_service import SearchService
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.website.website_paid import website_is_paid
from library.ai_intent_parser import parse_intent
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_type import StalkerDocumentType
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.api_key_routes import bp as api_key_bp
from library.auth import resolve_api_key
from library.chunk_review_routes import bp as chunk_review_bp
from library.reader_routes import bp as reader_bp
from library.youtube_processing import process_youtube_url

logging.basicConfig(level=logging.INFO)

cfg = load_config()

secrets_backend = cfg.require("SECRETS_BACKEND", "env")

APP_VERSION = "0.3.14.0"
BUILD_TIME = "2026.07.04 08:00"

logging.info(f"APP VERSION={APP_VERSION} (build time:{BUILD_TIME})")

if secrets_backend == "env":
    env_data = cfg.require("ENV_DATA")
    logging.info("ENV_DATA: %s", env_data)
elif secrets_backend == "vault":
    logging.info("Secrets loaded from Vault (ENV_DATA not required)")
elif secrets_backend == "aws":
    logging.info("Secrets loaded from AWS SSM (ENV_DATA not required)")

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
    """Resolve the 'x-api-key' header to an AuthContext (api_keys table with
    in-process cache) and store it in flask.g.auth."""
    api_key = request.headers.get('x-api-key')
    if api_key is None:
        abort(401, 'x-api-key header is missing')
    auth = resolve_api_key(get_scoped_session, api_key)
    if auth is None:
        abort(401, 'x-api-key header is wrong')
    g.auth = auth


logging.info("Starting flask application")
app = Flask(__name__)
logging.info("Flask - enabling CORS for all routes")
CORS(app)  # This will enable CORS for all routes

app.register_blueprint(chunk_review_bp)
app.register_blueprint(reader_bp)
app.register_blueprint(api_key_bp)


@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up scoped session at end of Flask request."""
    get_scoped_session().remove()


@app.before_request
def before_request_func():
    exempt_paths = ['/', '/healthz', '/startup', '/readiness', '/liveness', '/version']
    if request.path not in exempt_paths and request.method != 'OPTIONS':
        check_auth_header()

@app.route('/', methods=['GET', 'OPTIONS'])
def root():
    """Landing page — HTML for browsers, JSON for API clients (Accept: application/json)."""
    if 'application/json' in request.headers.get('Accept', ''):
        return {
            "status": "success",
            "message": "Stalker Web Documents API",
            "app_version": APP_VERSION,
            "app_build_time": BUILD_TIME,
            "encoding": "utf8",
        }, 200

    from flask import Response
    html = f"""<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"><title>Lenie AI</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;background:#f8fafc;color:#1e293b;min-height:100vh;padding:40px 20px}}
.container{{max-width:700px;margin:0 auto}}
h1{{font-size:1.6em;font-weight:700;margin-bottom:4px}}
.version{{color:#94a3b8;font-size:0.85em;margin-bottom:32px}}
.section{{margin-bottom:28px}}
.section h2{{font-size:0.8em;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:#64748b;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #e2e8f0}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 18px;
  text-decoration:none;color:#1e293b;transition:border-color .15s,box-shadow .15s}}
.card:hover{{border-color:#0369a1;box-shadow:0 2px 8px rgba(3,105,161,.1)}}
.card-title{{font-size:0.95em;font-weight:600;margin-bottom:3px}}
.card-desc{{font-size:0.8em;color:#64748b}}
.card.ext .card-title::after{{content:" ↗";color:#94a3b8;font-weight:400}}
.api-key-box{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 18px}}
label{{font-size:0.85em;font-weight:600;display:block;margin-bottom:6px}}
input{{width:100%;padding:8px 10px;border:1px solid #cbd5e1;border-radius:5px;
  font-size:0.88em;margin-bottom:8px}}
.saved{{color:#16a34a;font-size:0.8em}}
button{{padding:8px 16px;background:#0369a1;color:#fff;border:none;border-radius:5px;
  font-size:0.88em;cursor:pointer;font-weight:600;white-space:nowrap}}
button:hover{{background:#0284c7}}
</style>
</head>
<body>
<div class="container">
  <h1>Lenie AI</h1>
  <p class="version">Wersja {APP_VERSION} &nbsp;·&nbsp; API serwer</p>

  <div class="section">
    <h2>Interfejsy użytkownika</h2>
    <div class="cards" id="ui-cards">
      <a class="card ext" id="link-frontend" href="#"><div class="card-title">Interfejs główny</div><div class="card-desc">Lista dokumentów, wyszukiwanie, edycja</div></a>
      <a class="card ext" id="link-admin" href="#"><div class="card-title">Panel administracyjny</div><div class="card-desc">Zarządzanie, infrastruktura AWS</div></a>
    </div>
  </div>

  <div class="section">
    <h2>Narzędzia API</h2>
    <div class="cards">
      <a class="card" href="/version"><div class="card-title">Wersja API</div><div class="card-desc">Informacje o wersji i czasie budowania</div></a>
    </div>
  </div>

  <div class="section">
    <h2>Klucz API</h2>
    <div class="api-key-box">
      <label>API key</label>
      <input type="password" id="api-key" placeholder="x-api-key">
      <span class="saved" id="saved-info" style="display:none">✓ Klucz zapisany</span>
    </div>
  </div>
</div>
<script>
(function() {{
  var host = window.location.hostname;
  document.getElementById('link-frontend').href = 'http://' + host + ':3000';
  document.getElementById('link-admin').href   = 'http://' + host + ':3001';

  var saved = localStorage.getItem('lenie_api_key');
  if (saved) {{
    document.getElementById('api-key').value = saved;
    document.getElementById('saved-info').style.display = 'inline';
  }}
  document.getElementById('api-key').addEventListener('change', function() {{
    if (this.value) {{
      localStorage.setItem('lenie_api_key', this.value);
      document.getElementById('saved-info').style.display = 'inline';
    }}
  }});
}})();
</script>
</body>
</html>"""
    return Response(html, mimetype='text/html')


@app.route('/url_add', methods=['POST', 'OPTIONS'])
def url_add():
    """Dodaje nowy URL do systemu z zapisywaniem treści HTML do S3 i danych do bazy."""
    if request.method == 'OPTIONS':
        return {'status': 'OK', 'message': 'CORS preflight'}, 200

    try:
        url_data = request.get_json()
        if not url_data:
            return {'status': 'error', 'message': 'No JSON data provided'}, 400

        url_data_print = url_data.copy()
        if 'text' in url_data_print:
            url_data_print['text'] = url_data_print['text'][:50]
        if 'html' in url_data_print:
            url_data_print['html'] = url_data_print['html'][:50]
        logging.info('Data received by API', extra={"body": url_data_print})

        session = get_scoped_session()
        service = DocumentService(session)
        doc = service.create_document(
            url=url_data.get("url", ""),
            url_type=url_data.get("type", ""),
            text=url_data.get("text", ""),
            html=url_data.get("html", ""),
            title=url_data.get("title", ""),
            language=url_data.get("language", ""),
            note=url_data.get("note", "default_note"),
            paywall=url_data.get("paywall", False),
            source=url_data.get("source", "own"),
            ai_summary=url_data.get("ai_summary", False),
            chapter_list=url_data.get("chapter_list", False),
        )
        return {
            'status': 'success',
            'message': f'Successfully saved document with ID: {doc.id}',
            'document_id': doc.id
        }, 200

    except ValueError as e:
        logging.error("Validation error in /url_add: %s", e)
        return {'status': 'error', 'message': 'Invalid request data'}, 400
    except RuntimeError as e:
        logging.error("Storage error in /url_add: %s", e)
        session.rollback()
        return {'status': 'error', 'message': 'A storage error occurred while processing the request'}, 500
    except Exception as e:
        logging.error("Unexpected error in /url_add: %s", e)
        session.rollback()
        return {'status': 'error', 'message': "An unexpected error occurred"}, 500


@app.route('/website_list', methods=['GET'])
def website_list():
    logging.debug("Getting list of websites")
    logging.debug(request.form)

    document_type = request.args.get('type', 'ALL')
    document_state = request.args.get('document_state', 'ALL')
    search_in_documents = request.args.get('search_in_document', '')
    only_missing_obsidian_notes = request.args.get('only_missing_obsidian_notes', '').lower() in ('1', 'true')
    only_has_obsidian_notes = request.args.get('only_has_obsidian_notes', '').lower() in ('1', 'true')
    logging.debug(document_type)

    session = get_scoped_session()
    repo = WebsitesDBPostgreSQL(session)
    list_kwargs = {
        "document_type": document_type,
        "document_state": document_state,
        "search_in_documents": search_in_documents,
        "only_missing_obsidian_notes": only_missing_obsidian_notes,
        "only_has_obsidian_notes": only_has_obsidian_notes,
    }
    websites_list = repo.get_list(**list_kwargs)
    websites_list_count = repo.get_list(**list_kwargs, count=True)
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


@app.route('/document_states', methods=['GET', 'OPTIONS'])
def get_document_states():
    logging.debug("Getting document states, types, and errors")
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    response = {
        "status": "success",
        "message": "Document states retrieved",
        "encoding": "utf8",
        "states": [s.name for s in StalkerDocumentStatus],
        "types": [t.name for t in StalkerDocumentType],
        "errors": [e.name for e in StalkerDocumentStatusError],
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

    return jsonify(response), 200


@app.route('/website_get', methods=['GET'])
def website_get_by_id():
    logging.debug("Getting website by id")

    link_id = request.args.get('id')
    if not link_id:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400

    try:
        link_id_int = int(link_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid ID parameter — must be a positive integer"}, 400

    if link_id_int <= 0:
        return {"status": "error", "message": "Invalid ID parameter — must be a positive integer"}, 400

    session = get_scoped_session()
    service = DocumentService(session)
    doc = service.get_document(link_id_int)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404
    return doc.dict(), 200


def _entities_doc_id(raw_id):
    """Validate the 'id' request value; returns (doc_id, None) or (None, error_response)."""
    if not raw_id:
        return None, ({"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400)
    try:
        doc_id = int(raw_id)
    except (ValueError, TypeError):
        return None, ({"status": "error", "message": "Invalid ID parameter — must be a positive integer"}, 400)
    if doc_id <= 0:
        return None, ({"status": "error", "message": "Invalid ID parameter — must be a positive integer"}, 400)
    return doc_id, None


@app.route('/website_entities', methods=['GET'])
def website_entities_get():
    """NER entities (persons/places) stored for a document — see docs/ner-integration-plan.md."""
    from library.entity_service import get_document_entities

    doc_id, error = _entities_doc_id(request.args.get('id'))
    if error:
        return error

    session = get_scoped_session()
    doc = WebDocument.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    return {"status": "success", "id": doc_id, "entities": get_document_entities(session, doc_id)}, 200


@app.route('/website_entities', methods=['POST'])
def website_entities_refresh():
    """Re-run NER on the document text, verify places and replace stored entities.

    First call after an ner_service restart can take up to ~90s (model load) —
    see ner_service/README.md. Place verification (geocoder + LLM relevance,
    stage 3) runs after the refresh and adds miejsce-* tags to the document;
    its failure does not fail the request.
    """
    from library.entity_service import get_document_entities, refresh_document_entities

    doc_id, error = _entities_doc_id(request.form.get('id') or (request.get_json(silent=True) or {}).get('id'))
    if error:
        return error

    session = get_scoped_session()
    doc = WebDocument.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    text = doc.text_md or doc.text or ""
    if not text.strip():
        return {"status": "error", "message": "Document has no text content"}, 400

    rows = refresh_document_entities(session, doc_id, text)
    session.commit()

    place_tags: list[str] = []
    if rows:
        try:
            from library.place_verification import verify_document_places

            summary = verify_document_places(session, doc, text)
            session.commit()
            place_tags = summary["tagged"]
        except Exception:
            session.rollback()
            logging.exception("place verification failed for doc %s", doc_id)

    return {
        "status": "success",
        "id": doc_id,
        "refreshed": len(rows),
        "place_tags": place_tags,
        "entities": get_document_entities(session, doc_id),
    }, 200


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
    next_id = int(next_data[0])
    next_type = next_data[1]
    logging.info("Next document to correct: id=%d", next_id)
    response = {
        "status": "success",
        "next_id": next_id,
        "next_type": next_type,
    }

    return response, 200


def _parse_search_text(req):
    """Extract search text from request (form, JSON, or args)."""
    if req.form:
        return req.form.get('search')
    elif req.json:
        return req.json.get('search')
    else:
        return req.args.get('search')


def _parse_search_params(req):
    """Extract search text and limit from request (form, JSON, or args)."""
    if req.form:
        return req.form.get('search'), req.form.get('limit')
    elif req.json:
        return req.json.get('search'), req.json.get('limit')
    else:
        return req.args.get('search'), req.args.get('limit')


@app.route('/ai_get_embedding', methods=['POST'])
def ai_get_embedding():
    text = _parse_search_text(request)

    service = SearchService(get_scoped_session())
    try:
        embedds = service.get_embedding(text)
    except Exception as e:
        logging.error("Error generating embedding: %s", e)
        return jsonify({"status": "error", "message": "Error generating embedding", "encoding": "utf8", "text": text}), 500

    return jsonify({"status": "success", "message": "Dane odczytane pomyślnie.", "encoding": "utf8", "text": text,
            "embedding": embedds}), 200


@app.route('/website_similar', methods=['POST'])
def search_similar():
    text, limit = _parse_search_params(request)

    session = get_scoped_session()
    service = SearchService(session)
    try:
        websites_list = service.search_similar(text, limit=int(limit) if limit else 3)
    except RuntimeError:
        logging.exception("Error searching for similar documents")
        return jsonify({"status": "error", "message": "Error searching for similar documents", "encoding": "utf8", "text": text,
                "websites": []}), 500

    return jsonify({"status": "success", "message": "Dane odczytane pomyślnie.", "encoding": "utf8", "text": text,
            "websites": websites_list}), 200


@app.route('/website_download_text_content', methods=['POST'])
def website_download_text_content():
    logging.debug("Downloading text content")
    if request.form:
        url = request.form.get('url')
    elif request.json:
        url = request.json['url']
    else:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'url'"}, 400

    if not url:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'url'"}, 400

    service = DocumentService(get_scoped_session())
    try:
        result = service.download_and_parse(url)
    except RuntimeError:
        logging.exception("Error while downloading and parsing URL %s", url)
        return {"status": "error", "message": "Internal server error while processing the URL", "encoding": "utf8"}, 500

    return jsonify({
        "status": "success",
        "message": "page downloaded",
        "encoding": "utf8",
        "text": result["text"],
        "content": result["text"],
        "title": result["title"],
        "summary": result["summary"],
        "url": url,
        "language": result["language"],
    }), 200


# Retry is only safe before a transcript has ever been captured — once a document
# reaches NEED_MANUAL_REVIEW (or later), process_youtube_url() would overwrite the
# already-reviewed text on a fresh run.
_YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES = {
    StalkerDocumentStatus.TEMPORARY_ERROR.name,
    StalkerDocumentStatus.URL_ADDED.name,
    StalkerDocumentStatus.NEED_TRANSCRIPTION.name,
}


@app.route('/website_youtube_retry_captions', methods=['POST'])
def website_youtube_retry_captions():
    """Retry downloading YouTube captions for a document stuck in a no-transcript
    state (e.g. document_state_error=CAPTIONS_FETCH_ERROR)."""
    doc_id = request.form.get('id')
    if not doc_id:
        json_data = request.get_json(silent=True) or {}
        doc_id = json_data.get('id')

    if not doc_id:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400

    try:
        doc_id_int = int(doc_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid ID parameter — must be a positive integer"}, 400

    session = get_scoped_session()
    service = DocumentService(session)
    doc = service.get_document(doc_id_int)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    if doc.document_type != StalkerDocumentType.youtube.name:
        return {"status": "error", "message": "Retry captions is only available for YouTube documents"}, 400

    if doc.document_state not in _YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES:
        return {
            "status": "error",
            "message": f"Document is in state '{doc.document_state}' — captions retry is only allowed "
                       f"before a transcript has been captured ({', '.join(sorted(_YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES))})",
        }, 409

    webshare_api_key = cfg.get("WEBSHARE_API_KEY")
    updated = process_youtube_url(
        session=session,
        youtube_url=doc.url,
        language=doc.language,
        chapter_list=doc.chapter_list,
        note=doc.note,
        source=doc.source,
        webshare_api_key=webshare_api_key,
    )

    return {
        "status": "success",
        "message": "Captions retry finished",
        "id": updated.id,
        "document_state": updated.document_state,
        "document_state_error": updated.document_state_error,
    }, 200


@app.route('/website_text_remove_not_needed', methods=['POST'])
def website_text_remove_not_needed():
    text = request.form.get('text')
    url = request.form.get('url')

    if not text:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400
    if not url:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'url'"}, 400

    service = DocumentService(get_scoped_session())
    return jsonify({
        "status": "success",
        "text": service.clean_text(url, text),
        "encoding": "utf8",
        "message": "Text cleaned",
    }), 200


@app.route('/website_split_for_embedding', methods=['POST'])
def website_split_for_embedding():
    text = request.form.get('text')
    chapters_list_text = request.form.get('chapter_list')

    if not text:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'text'"}, 400

    service = DocumentService(get_scoped_session())
    return jsonify({
        "status": "success",
        "text": service.split_for_embedding(text, chapters_list_text),
        "encoding": "utf8",
        "message": "Text corrected",
    }), 200


@app.route('/website_delete', methods=['GET'])
def website_delete():
    link_id = request.args.get('id')
    if not link_id:
        return {"status": "error", "message": "Brakujące dane. Upewnij się, że dostarczasz 'id'"}, 400

    session = get_scoped_session()
    service = DocumentService(session)
    try:
        deleted = service.delete_document(int(link_id))
        if not deleted:
            return {"status": "success", "message": "Page doesn't exist in database", "encoding": "utf8"}, 200
        return {"status": "success", "message": "Page has been deleted from database", "encoding": "utf8"}, 200
    except Exception as e:
        session.rollback()
        logging.error("Failed to delete document: %s", e)
        return {"status": "error", "message": "Failed to delete document"}, 500


@app.route('/website_save', methods=['POST'])
def website_save():
    url = request.form.get('url')
    if not url:
        return {"status": "error", "message": "Missing data. Make sure you provide 'url'"}, 400

    link_id = request.form.get('id')
    attrs = {}
    for attr in ('text', 'title', 'language', 'tags', 'summary', 'source', 'author', 'note'):
        value = request.form.get(attr)
        if value is not None:
            attrs[attr] = value

    session = get_scoped_session()
    service = DocumentService(session)
    try:
        doc = service.save_document(
            url=url,
            link_id=int(link_id) if link_id else None,
            document_state=request.form.get('document_state'),
            document_type=request.form.get('document_type'),
            **attrs,
        )
        return {"status": "success", "message": f"Dane strony {doc.id} zaktualizowane pomyślnie."}, 200
    except ValueError as e:
        logging.error("Validation error in /website_save: %s", e)
        return jsonify({"status": "error", "message": "Invalid document type provided."}), 400
    except Exception as e:
        session.rollback()
        logging.error("Failed to save document: %s", e)
        return {"status": "error", "message": "Failed to save document"}, 500


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


@app.route('/transcription_usage', methods=['GET'])
def transcription_usage():
    """Return transcription usage summary and remaining budget."""
    session = get_scoped_session()
    summary = TranscriptionLog.get_usage_summary(session)
    balance_initial = float(cfg.get("TRANSCRIPTION_BALANCE_USD", "50.00") or "50.00")
    summary["balance_initial_usd"] = balance_initial
    summary["balance_remaining_usd"] = round(balance_initial - summary["total_spent_usd"], 4)
    return {"status": "success", **summary}, 200


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
    # Default bind on all interfaces is intentional — the server runs in a container
    bind_host = cfg.require("BIND_HOST", "0.0.0.0")  # nosec B104
    if cfg.require("USE_SSL", "false") == "true":
        logging.debug("Using SSL")
        app.run(debug=cfg.require("DEBUG", "false").lower() == "true", host=bind_host, port=port, ssl_context='adhoc')
    else:
        logging.debug("Using HTTP")
        app.run(debug=cfg.require("DEBUG", "false").lower() == "true", port=port, host=bind_host)
