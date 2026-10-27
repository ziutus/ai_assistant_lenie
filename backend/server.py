from library.browse_event_transport import browse_execution
from flask import Flask, Response, g, request, abort, jsonify
from flask_cors import CORS
import logging
import json
import os
from sqlalchemy import select

from library.config_loader import load_config
from library.db.engine import get_scoped_session
from library.db.models import ContentGroup, TranscriptionLog, Document, EmailFooterRule
from library.email_footer_rules import apply_footer_rule, normalize_sender_email
from library.document_service import DocumentService
from library.document_ingest_service import DocumentIngestService, IngestRequest
from library.search_service import SearchService
from library.document_repository import DocumentRepository
from library.website.website_paid import website_is_paid
from library.ai_intent_parser import parse_intent
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_type import StalkerDocumentType
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.api_key_routes import bp as api_key_bp
from library.auth import is_read_only_request_allowed, resolve_api_key
from library.chunk_review_routes import bp as chunk_review_bp, start_analysis_worker
from library.llm_cost_routes import bp as llm_cost_bp
from library.service_status_routes import bp as service_status_bp
from library.reader_routes import bp as reader_bp
from library.search_routes import bp as search_bp
from library.stats_routes import bp as stats_bp
from library.feed_routes import bp as feed_bp
from library.prompt_template_routes import bp as prompt_template_bp
from library.feed_monitor_service import link_matching_feed_items_to_document
from library.tool_candidate_routes import bp as tool_candidate_bp
from library.tool_recommendation_routes import bp as tool_recommendation_bp
from library.tool_routes import bp as tool_bp
from library.public_person_routes import bp as public_person_bp
from library.llm_analysis_routes import bp as llm_analysis_bp
from library.contact_routes import bp as contact_bp
from library.document_links_routes import bp as document_links_bp
from library.project_card_routes import bp as project_cards_bp
from library.recipe_routes import bp as recipes_bp
from library.topic_routes import bp as topics_bp
from library.cleanup_rules_routes import bp as cleanup_rules_bp
from library.transcript_corrections_routes import bp as transcript_corrections_bp
from library.chat_routes import bp as chat_bp
from library.place_routes import bp as places_bp
from library.ner_channel_glossary_routes import bp as ner_channel_glossary_bp
from library.obsidian_vault_routes import bp as obsidian_vault_bp
from library.ner_gazetteer_routes import bp as ner_gazetteer_bp
from library.youtube_processing import process_youtube_url, parse_chapters_from_description
from library.stalker_youtube_file import StalkerYoutubeFile
from library.storage import storage_from_config
from library.upload_storage import list_uploaded_files, store_uploaded_file

logging.basicConfig(level=logging.INFO)

cfg = load_config()

secrets_backend = cfg.require("SECRETS_BACKEND", "env")

APP_VERSION = "0.3.15.8"
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
    if not is_read_only_request_allowed(auth, request.method):
        abort(403, 'read-only API key may only use GET, HEAD or OPTIONS')
    g.auth = auth


logging.info("Starting flask application")
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(cfg.get("UPLOAD_MAX_BYTES") or 250 * 1024 * 1024)
logging.info("Flask - enabling CORS for all routes")
CORS(app)  # This will enable CORS for all routes

app.register_blueprint(chunk_review_bp)
app.register_blueprint(llm_cost_bp)
app.register_blueprint(service_status_bp)
app.register_blueprint(reader_bp)
app.register_blueprint(api_key_bp)
app.register_blueprint(search_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(feed_bp)
app.register_blueprint(prompt_template_bp)
app.register_blueprint(tool_candidate_bp)
app.register_blueprint(tool_recommendation_bp)
app.register_blueprint(tool_bp)
app.register_blueprint(public_person_bp)
app.register_blueprint(llm_analysis_bp)
app.register_blueprint(contact_bp)
app.register_blueprint(document_links_bp)
app.register_blueprint(project_cards_bp)
app.register_blueprint(recipes_bp)
app.register_blueprint(topics_bp)
app.register_blueprint(cleanup_rules_bp)
app.register_blueprint(transcript_corrections_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(places_bp)
app.register_blueprint(ner_gazetteer_bp)
app.register_blueprint(ner_channel_glossary_bp)
app.register_blueprint(obsidian_vault_bp)
start_analysis_worker()


@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up scoped session at end of Flask request."""
    get_scoped_session().remove()


@app.before_request
def before_request_func():
    exempt_paths = ['/', '/healthz', '/startup', '/readiness', '/liveness', '/version']
    if request.path not in exempt_paths and request.method != 'OPTIONS':
        check_auth_header()


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(error="file is too large"), 413


@app.route('/upload-file', methods=['POST', 'OPTIONS'])
def upload_file():
    """Put a PDF/EPUB/MOBI into the durable, importer-facing upload area."""
    # Browsers send a CORS preflight because the actual upload carries the
    # custom x-api-key header. Do not fall through to request.files here: that
    # made the preflight return 400, so the browser never issued the POST.
    if request.method == 'OPTIONS':
        return '', 204
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="multipart field 'file' is required"), 400
    try:
        result = store_uploaded_file(storage_from_config(cfg), uploaded.filename, uploaded.read())
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:  # noqa: BLE001 - storage details must not leak to the browser
        logging.exception("Could not store uploaded file")
        return jsonify(error="could not store file"), 502
    return jsonify(
        key=result.key,
        filename=result.filename,
        size=result.size,
        format=result.extension.removeprefix("."),
    ), 201


@app.route('/uploads', methods=['GET', 'OPTIONS'])
def list_uploads():
    """List importer-facing files staged in ObjectStorage/MinIO."""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 200)
    except ValueError:
        return jsonify(error="limit must be an integer"), 400
    try:
        uploads = list_uploaded_files(storage_from_config(cfg), limit)
    except Exception:  # noqa: BLE001 - storage details must not leak to API clients
        logging.exception("Could not list uploaded files")
        return jsonify(error="could not list uploaded files"), 502
    return jsonify({
        "uploads": [
            {"key": item.key, "filename": item.filename, "size": item.size, "format": item.extension.removeprefix(".")}
            for item in uploads
        ],
        "limit": limit,
    })

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
        if url_data.get("type") == "email":
            # Mail content is private.  Keep useful diagnostics without
            # leaking even a preview into server logs.
            url_data_print.pop("text", None)
            url_data_print.pop("html", None)
            url_data_print["text_length"] = len(url_data.get("text") or "")
        else:
            if 'text' in url_data_print:
                url_data_print['text'] = url_data_print['text'][:50]
            if 'html' in url_data_print:
                url_data_print['html'] = url_data_print['html'][:50]
        logging.info('Data received by API', extra={"body": url_data_print})

        session = get_scoped_session()
        result = DocumentIngestService(session).ingest(
            IngestRequest(
                url=url_data.get("url", ""),
                document_type=url_data.get("type", ""),
                text=url_data.get("text", ""),
                html=url_data.get("html", ""),
                title=url_data.get("title", ""),
                language=url_data.get("language", ""),
                note=url_data.get("note", "default_note"),
                paywall=url_data.get("paywall", False),
                requires_login=url_data.get("requires_login"),
                social_platform=url_data.get("social_platform"),
                source=url_data.get("source", "own"),
                ai_summary=url_data.get("ai_summary", False),
                chapter_list=url_data.get("chapter_list", False),
                byline=url_data.get("byline", ""),
                email_sender=url_data.get("email_sender"),
                images=url_data.get("images"),
                original_id=url_data.get("original_id"),
                published_on=url_data.get("published_on"),
                operation=url_data.get("operation", "create"),
                external_uuid=url_data.get("external_uuid"),
                ingested_at=url_data.get("ingested_at"),
            ),
            initiated_by_user_id=getattr(getattr(g, "auth", None), "user_id", None),
        )
        doc = session.get(Document, result.document_id)
        link_matching_feed_items_to_document(session, doc)
        session.commit()
        if result.status == "already_exists":
            return {
                'status': 'already_exists',
                'message': f'Document already exists with ID: {doc.id}',
                'document_id': doc.id,
                'missing_raw_html': result.missing_raw_html,
                'existing_document_type': result.existing_document_type,
            }, 409
        return {
            'status': 'updated' if result.status == 'updated' else 'success',
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
@browse_execution('document_list')
def website_list():
    logging.debug("Getting list of websites")
    logging.debug(request.form)

    document_type = request.args.get('type', 'ALL')
    processing_status = request.args.get('processing_status', 'ALL')
    search_in_documents = request.args.get('search_in_document', '')
    only_missing_obsidian_notes = request.args.get('only_missing_obsidian_notes', '').lower() in ('1', 'true')
    only_has_obsidian_notes = request.args.get('only_has_obsidian_notes', '').lower() in ('1', 'true')
    without_embedding = request.args.get('without_embedding', '').lower() in ('1', 'true')
    try:
        topic_group_ids = [int(value) for value in request.args.get('topic_group_ids', '').split(',') if value]
        priority_group_id = int(request.args['priority_group_id']) if request.args.get('priority_group_id') else None
        topic_match = request.args.get('topic_match', 'any')
        sort = request.args.get('sort', 'newest')
        without_topics = request.args.get('without_topics', '').lower() in ('1', 'true')
        topic_filter_active = request.args.get('topic_filter', '').lower() in ('1', 'true')
        include_without_topics = request.args.get('include_without_topics', '').lower() in ('1', 'true')
        without_priority = request.args.get('without_priority', '').lower() in ('1', 'true')
        if len(topic_group_ids) != len(set(topic_group_ids)) or topic_match not in {'any', 'all'} or sort not in {'newest', 'priority'}:
            raise ValueError
        if (topic_group_ids and without_topics and not topic_filter_active) or priority_group_id and without_priority:
            raise ValueError
    except (TypeError, ValueError):
        return {"status": "error", "message": "invalid content group filter"}, 400
    try:
        limit = min(max(int(request.args.get('limit', 100)), 1), 100)
        page = max(int(request.args.get('page', 1)), 1)
    except (TypeError, ValueError):
        return {"status": "error", "message": "limit and page must be integers"}, 400
    logging.debug(document_type)

    session = get_scoped_session()
    group_ids = topic_group_ids + ([priority_group_id] if priority_group_id else [])
    if group_ids:
        groups = {group.id: group for group in session.scalars(select(ContentGroup).where(ContentGroup.id.in_(group_ids), ContentGroup.archived_at.is_(None))).all()}
        if len(groups) != len(group_ids) or any(groups[group_id].kind != 'topic' for group_id in topic_group_ids) or (priority_group_id and groups[priority_group_id].kind != 'priority'):
            return {"status": "error", "message": "invalid content group filter"}, 400
    repo = DocumentRepository(session)
    list_kwargs = {
        "document_type": document_type,
        "processing_status": processing_status,
        "search_in_documents": search_in_documents,
        "only_missing_obsidian_notes": only_missing_obsidian_notes,
        "only_has_obsidian_notes": only_has_obsidian_notes,
        "without_embedding": without_embedding,
        "limit": limit,
        "offset": page - 1,
        "topic_group_ids": topic_group_ids,
        "topic_match": topic_match,
        "priority_group_id": priority_group_id,
        "without_topics": without_topics,
        "topic_filter_active": topic_filter_active,
        "include_without_topics": include_without_topics,
        "without_priority": without_priority,
        "sort": sort,
    }
    g.browse_event.update(
        filters={key: value for key, value in list_kwargs.items()
                 if key not in {"limit", "offset", "sort", "search_in_documents"}},
        query_text=search_in_documents, effective_query=search_in_documents,
        sort=sort, page_size=limit, offset=(page - 1) * limit,
    )
    if not topic_filter_active:
        g.browse_event["filters"].update(topic_group_ids=[], include_without_topics=False, topic_match="any")
    try:
        websites_list = repo.get_list(**list_kwargs)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    count_kwargs = {key: value for key, value in list_kwargs.items() if key not in ("limit", "offset")}
    websites_list_count = repo.get_list(**count_kwargs, count=True)
    logging.debug("website count: %s", websites_list_count)

    response = {
        "status": "success",
        "message": "Dane odczytane pomyślnie.",
        "encoding": "utf8",
        "websites": websites_list,
        "all_results_count": websites_list_count,
        "pagination": {
            "page": page,
            "page_size": limit,
            "total_pages": max(1, (websites_list_count + limit - 1) // limit),
        },
    }

    return response, 200


@app.route('/website_list_neighbors', methods=['GET'])
def website_list_neighbors():
    """Return adjacent document ids within the same filtered /website_list result."""
    try:
        document_id = int(request.args['document_id'])
        document_type = request.args.get('type', 'ALL')
        processing_status = request.args.get('processing_status', 'ALL')
        # The reader receives the shareable /list URL, where the search field
        # is named ``q``.  Keep ``search_in_document`` for direct API clients.
        search_in_documents = request.args.get('q', request.args.get('search_in_document', ''))
        only_missing_obsidian_notes = request.args.get('only_missing_obsidian_notes', '').lower() in ('1', 'true')
        only_has_obsidian_notes = request.args.get('only_has_obsidian_notes', '').lower() in ('1', 'true')
        without_embedding = request.args.get('without_embedding', '').lower() in ('1', 'true')
        topic_group_ids = [int(value) for value in request.args.get('topic_group_ids', '').split(',') if value]
        priority_group_id = int(request.args['priority_group_id']) if request.args.get('priority_group_id') else None
        topic_match = request.args.get('topic_match', 'any')
        sort = request.args.get('sort', 'newest')
        without_topics = request.args.get('without_topics', '').lower() in ('1', 'true')
        topic_filter_active = request.args.get('topic_filter', '').lower() in ('1', 'true')
        include_without_topics = request.args.get('include_without_topics', '').lower() in ('1', 'true')
        without_priority = request.args.get('without_priority', '').lower() in ('1', 'true')
        if len(topic_group_ids) != len(set(topic_group_ids)) or topic_match not in {'any', 'all'} or sort not in {'newest', 'priority'}:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return {"status": "error", "message": "invalid list navigation filter"}, 400

    repo = DocumentRepository(get_scoped_session())
    filters = {
        "document_type": document_type, "processing_status": processing_status,
        "search_in_documents": search_in_documents, "only_missing_obsidian_notes": only_missing_obsidian_notes,
        "only_has_obsidian_notes": only_has_obsidian_notes, "without_embedding": without_embedding,
        "topic_group_ids": topic_group_ids, "topic_match": topic_match, "priority_group_id": priority_group_id,
        "without_topics": without_topics, "topic_filter_active": topic_filter_active,
        "include_without_topics": include_without_topics, "without_priority": without_priority, "sort": sort,
    }
    try:
        total = repo.get_list(**filters, count=True)
        ids: list[int] = []
        for offset in range((total + 99) // 100):
            ids.extend(row["id"] for row in repo.get_list(**filters, limit=100, offset=offset))
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    try:
        index = ids.index(document_id)
    except ValueError:
        return {"status": "success", "previous_id": None, "next_id": None}
    return {"status": "success", "previous_id": ids[index - 1] if index else None,
            "next_id": ids[index + 1] if index + 1 < len(ids) else None}


@app.route('/website_count', methods=['GET'])
def website_count():
    """Return document counts grouped by type in a single query."""
    logging.debug("Getting document counts by type")
    session = get_scoped_session()
    repo = DocumentRepository(session)
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

    include_text = request.args.get('include_text', '1') != '0'

    session = get_scoped_session()
    service = DocumentService(session)
    doc = service.get_document(link_id_int)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    # Real embedding stats for the editor: embeddings actually stored for the
    # document + approved TEMAT chunks (the source of new embeddings via
    # POST /analysis_run/<id>/generate_embeddings). Replaces the old frontend
    # guess based on counting "\n\n\n" separators.
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import DocumentAnalysisRun, DocumentChunk, DocumentEmbedding

    result = doc.dict()
    # text_length reflects the same text/text_raw fallback callers use to read
    # content — computed before include_text=0 strips the fields below, so
    # cheap metadata-only calls (e.g. /lenie-obsidian-note Step 1a) can still branch
    # on document length without paying for the full text payload.
    result["text_length"] = len(doc.text or doc.text_raw or "")
    if not include_text:
        result.pop("text", None)
        result.pop("text_raw", None)
        result.pop("text_md", None)
    result["embeddings_count"] = session.execute(
        sa_select(sa_func.count()).select_from(DocumentEmbedding)
        .where(DocumentEmbedding.document_id == link_id_int)
    ).scalar()
    result["content_locked"] = bool(result["embeddings_count"])
    result["approved_chunks_count"] = session.execute(
        sa_select(sa_func.count()).select_from(DocumentChunk)
        .where(DocumentChunk.document_id == link_id_int,
               DocumentChunk.type == "TEMAT",
               DocumentChunk.status == "approved")
    ).scalar()
    latest_run_id = session.execute(
        sa_select(sa_func.max(DocumentAnalysisRun.id))
        .where(
            DocumentAnalysisRun.document_id == link_id_int,
            DocumentAnalysisRun.status != "superseded",
        )
    ).scalar()
    result["analysis_run_id"] = latest_run_id
    if latest_run_id is None:
        result["analysis_chunks_count"] = 0
        result["pending_chunks_count"] = 0
    else:
        result["analysis_chunks_count"] = session.execute(
            sa_select(sa_func.count()).select_from(DocumentChunk)
            .where(DocumentChunk.run_id == latest_run_id)
        ).scalar()
        result["pending_chunks_count"] = session.execute(
            sa_select(sa_func.count()).select_from(DocumentChunk)
            .where(
                DocumentChunk.run_id == latest_run_id,
                DocumentChunk.status.in_((
                    "pending", "needs_reanalysis", "split_requested", "split",
                )),
            )
        ).scalar()
    return result, 200


@app.route('/document/<int:doc_id>/reopen_editing', methods=['POST'])
def reopen_document_editing(doc_id: int):
    """Explicitly invalidate derived data before allowing content edits again."""
    from library.document_editing import reopen_document_for_editing

    session = get_scoped_session()
    try:
        result = reopen_document_for_editing(session, doc_id)
    except LookupError:
        return {"status": "error", "message": "Document not found"}, 404
    except RuntimeError as exc:
        return {"status": "error", "message": str(exc)}, 409
    except Exception:
        session.rollback()
        logging.exception("failed to reopen document %s for editing", doc_id)
        return {"status": "error", "message": "Failed to reopen document for editing"}, 500
    return {"status": "success", **result}, 200


@app.route('/document/<int:doc_id>/countries/detect', methods=['POST'])
def detect_countries_for_document(doc_id: int):
    """Detect country tags independently of chunk analysis."""
    from sqlalchemy.exc import SQLAlchemyError

    from library.document_countries import detect_document_countries

    session = get_scoped_session()
    try:
        result = detect_document_countries(session, doc_id)
    except LookupError as exc:
        return {"status": "error", "message": str(exc)}, 404
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    except SQLAlchemyError:
        session.rollback()
        logging.exception("country detection database error for document %s", doc_id)
        return {"status": "error", "message": "Failed to save document countries"}, 500
    return {"status": "success", **result}, 200


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
    from library.document_countries import countries_from_tags

    doc_id, error = _entities_doc_id(request.args.get('id'))
    if error:
        return error

    session = get_scoped_session()
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    return {
        "status": "success",
        "id": doc_id,
        "entities": get_document_entities(session, doc_id),
        "countries": countries_from_tags(doc.tags),
        # miejsce-* tags are the verified-places summary stored in Document.tags;
        # read-only here (the panel shows them next to the place chips).
        "place_tags": sorted(
            tag.strip() for tag in (doc.tags if isinstance(doc.tags, str) else "").split(",")
            if tag.strip().startswith("miejsce-")
        ),
        "ner_unavailable_at": doc.ner_unavailable_at.isoformat() if doc.ner_unavailable_at else None,
        "entities_checked_at": doc.entities_checked_at.isoformat() if doc.entities_checked_at else None,
    }, 200


@app.route('/website_entities/enrichment_job', methods=['GET'])
def website_entities_enrichment_job_get():
    """Latest entity-enrichment job for a document, for editor polling."""
    from library.db.models import Job
    from library.entity_enrichment_service import ENTITY_ENRICHMENT, job_view

    doc_id, error = _entities_doc_id(request.args.get('id'))
    if error:
        return error
    session = get_scoped_session()
    if Document.get_by_id(session, doc_id) is None:
        return {"status": "error", "message": "Document not found"}, 404
    job = session.scalars(
        select(Job)
        .where(Job.type == ENTITY_ENRICHMENT, Job.parameters["document_id"].as_integer() == doc_id)
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()
    return {"status": "success", "job": job_view(job) if job else None}, 200


@app.route('/website_entities', methods=['POST'])
def website_entities_refresh():
    """Re-run NER and enqueue the slow entity verification stages.

    First call after an ner_service restart can take up to ~90s (model load) —
    see ner_service/README.md. Geocoding, person resolution and pipeline lookup
    run in the worker after this response, so one editor click starts the whole
    analysis without holding the browser request open.
    """
    from sqlalchemy.exc import OperationalError

    from library.entity_service import get_document_entities, refresh_document_entities
    from library.entity_text import document_ner_text
    from library.ner_client import NERServiceUnavailable

    doc_id, error = _entities_doc_id(request.form.get('id') or (request.get_json(silent=True) or {}).get('id'))
    if error:
        return error

    session = get_scoped_session()
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    text = document_ner_text(doc)
    if not text.strip():
        message = ("Wszystkie rozdziały są wykluczone z NER (reklama/szum/źródła)"
                   if (doc.text_md or doc.text or "").strip() else "Document has no text content")
        return {"status": "error", "message": message}, 400
    from library.document_editing import document_has_embeddings
    if document_has_embeddings(session, doc_id):
        return {
            "status": "error",
            "message": "Document has embeddings. Reopen it for editing before refreshing entities.",
        }, 409

    try:
        rows = refresh_document_entities(session, doc_id, text)
    except NERServiceUnavailable:
        # refresh_document_entities already committed doc.ner_unavailable_at.
        return {
            "status": "error",
            "message": "Serwis NER jest niedostępny — spróbuj ponownie za chwilę.",
            "ner_unavailable": True,
        }, 503
    except OperationalError as exc:
        session.rollback()
        if getattr(exc.orig, "pgcode", None) == "40P01":
            return {
                "status": "error",
                "message": "Encje tego dokumentu są właśnie odświeżane. Spróbuj ponownie za chwilę.",
            }, 409
        logging.exception("database error while refreshing entities for doc %s", doc_id)
        return {"status": "error", "message": "Nie udało się zapisać odświeżonych encji."}, 500
    except Exception:
        session.rollback()
        logging.exception("entity refresh failed for doc %s", doc_id)
        return {"status": "error", "message": "Nie udało się odświeżyć encji."}, 500
    session.commit()

    enrichment_job = None
    if rows:
        from library.entity_enrichment_service import ensure_entity_enrichment_job, job_view

        enrichment_job = ensure_entity_enrichment_job(
            session, doc, user_id=getattr(getattr(g, "auth", None), "user_id", None),
        )

    return {
        "status": "success",
        "id": doc_id,
        "refreshed": len(rows),
        "enrichment_job": job_view(enrichment_job) if enrichment_job else None,
        "entities": get_document_entities(session, doc_id),
    }, 202


@app.route('/persons', methods=['GET'])
def persons_search():
    """Search the person registry (NER stage 4) — fuzzy by name/alias (?q=), or list newest."""
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import Person, PersonAlias

    from library import knowledge_sources

    session = get_scoped_session()
    query = (request.args.get('q') or "").strip()
    kind = (request.args.get('kind') or "").strip()  # kind=public: the public figures the user follows
    if query:
        by_name = session.execute(
            sa_select(Person)
            .where(sa_func.similarity(Person.canonical_name, query) > 0.3)
            .order_by(sa_func.similarity(Person.canonical_name, query).desc())
            .limit(20)
        ).scalars().all()
        by_alias = session.execute(
            sa_select(Person)
            .join(PersonAlias, PersonAlias.person_id == Person.id)
            .where(sa_func.similarity(PersonAlias.alias, query) > 0.3)
            .limit(20)
        ).scalars().all()
        seen: set[int] = set()
        persons = [p for p in list(by_name) + list(by_alias) if p.id not in seen and not seen.add(p.id)]
        if kind:
            persons = [p for p in persons if p.kind == kind]
    elif kind:
        persons = session.execute(
            sa_select(Person).where(Person.kind == kind).order_by(Person.canonical_name)
        ).scalars().all()
    else:
        persons = session.execute(
            sa_select(Person).order_by(Person.created_at.desc()).limit(50)
        ).scalars().all()

    total = len(persons)
    offset = max(request.args.get('offset', 0, type=int), 0)
    limit = min(max(request.args.get('limit', 50, type=int), 1), 100)
    persons = persons[offset:offset + limit]
    sources = knowledge_sources.sources_for_persons(session, [p.id for p in persons])
    return {
        "status": "success",
        "total": total, "limit": limit, "offset": offset,
        "persons": [
            {
                "id": p.id, "uuid": p.uuid, "canonical_name": p.canonical_name,
                "wikidata_qid": p.wikidata_qid, "description": p.description,
                "long_description": p.long_description, "links": p.links or [],
                "aliases": [a.alias for a in p.aliases],
                **knowledge_sources.person_fields(p), "sources": sources.get(p.id, []),
            }
            for p in persons
        ],
    }, 200


@app.route('/person_documents', methods=['GET'])
def person_documents():
    """All documents mentioning a person (?id=<person_id>) — the stage-4 user goal.

    Each document carries mention_count (from document_entities, matched by the
    link's raw_mention) and the list is sorted by it — the person page shows
    where the person is actually discussed, not just referenced once. A count
    of 0 means the entity row is gone (entities were refreshed after linking).
    """
    from sqlalchemy import select as sa_select
    from library.db.models import DocumentEntity, DocumentPerson, Person

    person_id, error = _entities_doc_id(request.args.get('id'))
    if error:
        return error

    session = get_scoped_session()
    person = session.get(Person, person_id)
    if person is None:
        return {"status": "error", "message": "Person not found"}, 404

    links = session.execute(
        sa_select(DocumentPerson).where(DocumentPerson.person_id == person_id)
    ).scalars().all()
    documents = []
    for link in links:
        mention_count = session.execute(
            sa_select(DocumentEntity.mention_count).where(
                DocumentEntity.document_id == link.document_id,
                DocumentEntity.entity_type == "persName",
                DocumentEntity.entity_text == link.raw_mention,
            )
        ).scalar_one_or_none() or 0
        documents.append({
            "id": link.document.id, "title": link.document.title,
            "document_type": link.document.document_type,
            "raw_mention": link.raw_mention, "confidence": link.confidence,
            "mention_count": mention_count, "role": link.role,
        })
    documents.sort(key=lambda d: (d["role"] != "author", -d["mention_count"]))
    from library import knowledge_sources

    return {
        "status": "success",
        "person": {"id": person.id, "canonical_name": person.canonical_name,
                   "description": person.description, "wikidata_qid": person.wikidata_qid,
                   "long_description": person.long_description, "links": person.links or [],
                   "aliases": [a.alias for a in person.aliases],
                   **knowledge_sources.person_fields(person),
                   "sources": knowledge_sources.sources_for_persons(session, [person.id]).get(person.id, [])},
        "documents": documents,
    }, 200


@app.route('/persons/<int:person_id>', methods=['PATCH', 'OPTIONS'])
def person_update(person_id: int):
    """Edit a registry person: ``canonical_name``, ``description``, ``wikidata_qid`` (``Q123`` or empty to
    clear) and ``aliases`` (the full list; absent key = unchanged). A renamed person keeps the old name as
    an alias, so documents that mention it still resolve."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    import re
    from sqlalchemy import select as sa_select
    from library import person_registry
    from library.db.models import Person

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return {"status": "error", "message": "JSON body required"}, 400
    session = get_scoped_session()
    person = session.get(Person, person_id)
    if person is None:
        return {"status": "error", "message": "Person not found"}, 404

    name = data.get('canonical_name')
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 500):
        return {"status": "error", "message": "Nieprawidłowe nazwisko."}, 400
    description = data.get('description')
    if description is not None and not isinstance(description, str):
        return {"status": "error", "message": "Nieprawidłowy opis."}, 400
    long_description = data.get('long_description')
    if long_description is not None and not isinstance(long_description, str):
        return {"status": "error", "message": "Nieprawidłowy długi opis."}, 400
    links = None
    if 'links' in data:
        from library.person_registry import normalize_person_links
        try:
            links = normalize_person_links(data['links'])
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}, 400
    qid = data.get('wikidata_qid')
    if qid is not None:
        qid = qid.strip() if isinstance(qid, str) else qid
        if qid and not (isinstance(qid, str) and re.fullmatch(r"Q\d{1,12}", qid)):
            return {"status": "error", "message": "Identyfikator Wikidata ma postać Q123."}, 400
    aliases = data.get('aliases')
    if aliases is not None and not (isinstance(aliases, list) and all(isinstance(a, str) for a in aliases)):
        return {"status": "error", "message": "Aliasy muszą być listą tekstów."}, 400
    from library import knowledge_sources

    try:
        public_fields = knowledge_sources.validate_person_fields(data)  # kind / role / obsidian_note_path
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400

    try:
        for field, value in public_fields.items():
            setattr(person, field, value)
        if qid:
            other = session.execute(sa_select(Person).where(
                Person.wikidata_qid == qid, Person.id != person_id)).scalars().first()
            if other is not None:
                # jsonify enforces Content-Type: application/json (CodeQL py/reflective-xss)
                return jsonify(status="error", message=f"Identyfikator {qid} ma już osoba „{other.canonical_name}”.",
                               conflict_person_id=other.id), 409
        if name is not None and name.strip() != person.canonical_name:
            old_name = person.canonical_name
            person.canonical_name = name.strip()
            person_registry.add_person_alias(session, person, old_name)
        if description is not None:
            person.description = description.strip() or None
        if long_description is not None:
            person.long_description = long_description.strip() or None
        if links is not None:
            person.links = links
        if 'wikidata_qid' in data:
            person.wikidata_qid = qid or None
        if aliases is not None:
            keep = {a.strip().lower() for a in aliases if a.strip()}
            for existing in list(person.aliases):
                if existing.alias.lower() not in keep:
                    session.delete(existing)
            session.flush()
            session.refresh(person)
            for alias in aliases:
                if alias.strip():
                    person_registry.add_person_alias(session, person, alias.strip())
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("person update failed for person %s", person_id)
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "person": {
        "id": person.id, "canonical_name": person.canonical_name, "description": person.description,
        "long_description": person.long_description, "links": person.links or [],
        "wikidata_qid": person.wikidata_qid, "aliases": [a.alias for a in person.aliases],
        **knowledge_sources.person_fields(person),
        "sources": knowledge_sources.sources_for_persons(session, [person.id]).get(person.id, [])}}), 200


@app.route('/persons_review', methods=['GET'])
def persons_review_list():
    """The manual_review queue — person links awaiting a human decision (NER stage 4)."""
    from library.person_registry import list_manual_review

    session = get_scoped_session()
    entries = list_manual_review(session)
    return {"status": "success", "count": len(entries), "entries": entries}, 200


@app.route('/person_biographies_review', methods=['GET'])
def person_biographies_review_list():
    """Author biographies whose new/conflicting facts need a human decision."""
    from library.author_biography import list_biography_review

    session = get_scoped_session()
    entries = list_biography_review(session)
    return {"status": "success", "count": len(entries), "entries": entries}, 200


@app.route('/person_biographies_review/<int:link_id>', methods=['PATCH', 'OPTIONS'])
def person_biographies_review_decide(link_id: int):
    """Approve the proposed merged description or reject the biography update."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.author_biography import decide_biography_review
    from library.db.models import DocumentPerson

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    link = session.get(DocumentPerson, link_id)
    if link is None:
        return {"status": "error", "message": "Review entry not found"}, 404
    try:
        result = decide_biography_review(link, data.get('action'))
        session.commit()
    except ValueError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}, 400
    except Exception:
        session.rollback()
        logging.exception("biography review decision failed for link %s", link_id)
        return {"status": "error", "message": "DB error"}, 500
    return {"status": "success", **result}, 200


@app.route('/information_sources', methods=['GET'])
def information_sources_list():
    """Search canonical information sources and return document counts."""
    from sqlalchemy import func, or_, select
    from library.db.models import (
        DocumentInformationSource, InformationSource, InformationSourceAlias,
    )

    session = get_scoped_session()
    query = (request.args.get('q') or '').strip()
    statement = (
        select(
            InformationSource,
            func.count(func.distinct(DocumentInformationSource.document_id)).label('document_count'),
        )
        .outerjoin(DocumentInformationSource, DocumentInformationSource.source_id == InformationSource.id)
        .group_by(InformationSource.id)
        .order_by(
            func.count(func.distinct(DocumentInformationSource.document_id)).desc(),
            InformationSource.canonical_name,
        )
    )
    if query:
        pattern = f"%{query}%"
        alias_match = select(InformationSourceAlias.source_id).where(
            InformationSourceAlias.alias.ilike(pattern)
        )
        statement = statement.where(or_(
            InformationSource.canonical_name.ilike(pattern),
            InformationSource.domain.ilike(pattern),
            InformationSource.id.in_(alias_match),
        ))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    offset = max(request.args.get('offset', 0, type=int), 0)
    limit = min(max(request.args.get('limit', 50, type=int), 1), 100)
    rows = session.execute(statement.offset(offset).limit(limit)).all()
    entries = [{
        "id": source.id,
        "canonical_name": source.canonical_name,
        "source_type": source.source_type,
        "domain": source.domain,
        "description": source.description,
        "aliases": [alias.alias for alias in source.aliases],
        "document_count": count,
    } for source, count in rows]
    return {"status": "success", "count": total, "total": total, "limit": limit, "offset": offset, "entries": entries}, 200


@app.route('/information_sources/<int:source_id>/documents', methods=['GET'])
def information_source_documents(source_id: int):
    """Return documents attributed to one source, optionally filtered by role."""
    from sqlalchemy import func, select
    from library.db.models import DocumentInformationSource, InformationSource

    session = get_scoped_session()
    source = session.get(InformationSource, source_id)
    if source is None:
        return {"status": "error", "message": "Information source not found"}, 404
    statement = select(DocumentInformationSource).where(
        DocumentInformationSource.source_id == source_id
    ).order_by(DocumentInformationSource.created_at.desc())
    role = (request.args.get('role') or '').strip()
    if role:
        statement = statement.where(DocumentInformationSource.role == role)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    offset = max(request.args.get('offset', 0, type=int), 0)
    limit = min(max(request.args.get('limit', 50, type=int), 1), 100)
    links = session.scalars(statement.offset(offset).limit(limit)).all()
    entries = [{
        "document_id": link.document_id,
        "title": link.document.title,
        "url": link.document.url,
        "role": link.role,
        "raw_mention": link.raw_mention,
        "source_url": link.source_url,
        "evidence_excerpt": link.evidence_excerpt,
        "confidence": link.confidence,
        "review_status": link.review_status,
    } for link in links]
    return {
        "status": "success",
        "source": {"id": source.id, "canonical_name": source.canonical_name, "domain": source.domain},
        "count": total,
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": entries,
    }, 200


@app.route('/information_sources/<int:source_id>/publisher_stats', methods=['GET'])
def information_source_publisher_stats(source_id: int):
    """Summarize external provenance for documents published by one source."""
    from sqlalchemy import func, select
    from library.db.models import DocumentInformationSource, InformationSource

    session = get_scoped_session()
    source = session.get(InformationSource, source_id)
    if source is None:
        return {"status": "error", "message": "Information source not found"}, 404

    published_ids = select(DocumentInformationSource.document_id).where(
        DocumentInformationSource.source_id == source_id,
        DocumentInformationSource.role == "publisher",
    )
    published_count = session.scalar(select(func.count()).select_from(published_ids.subquery())) or 0
    external_document_count = session.scalar(select(
        func.count(func.distinct(DocumentInformationSource.document_id))
    ).where(
        DocumentInformationSource.document_id.in_(published_ids),
        DocumentInformationSource.role != "publisher",
    )) or 0
    role_rows = session.execute(select(
        DocumentInformationSource.role,
        func.count(func.distinct(DocumentInformationSource.document_id)),
    ).where(
        DocumentInformationSource.document_id.in_(published_ids),
        DocumentInformationSource.role != "publisher",
    ).group_by(DocumentInformationSource.role)).all()
    origin_rows = session.execute(select(
        InformationSource.id,
        InformationSource.canonical_name,
        DocumentInformationSource.role,
        func.count(func.distinct(DocumentInformationSource.document_id)),
    ).join(
        DocumentInformationSource, DocumentInformationSource.source_id == InformationSource.id,
    ).where(
        DocumentInformationSource.document_id.in_(published_ids),
        DocumentInformationSource.role != "publisher",
    ).group_by(
        InformationSource.id, InformationSource.canonical_name, DocumentInformationSource.role,
    ).order_by(func.count(func.distinct(DocumentInformationSource.document_id)).desc())).all()

    return {
        "status": "success",
        "source": {"id": source.id, "canonical_name": source.canonical_name, "domain": source.domain},
        "published_document_count": published_count,
        # Absence of a detected source is not proof that reporting is original.
        "without_external_source_count": max(0, published_count - external_document_count),
        "with_external_source_count": external_document_count,
        "role_counts": {role: count for role, count in role_rows},
        "origins": [{
            "source_id": origin_id,
            "canonical_name": name,
            "role": role,
            "document_count": count,
        } for origin_id, name, role, count in origin_rows],
    }, 200


@app.route('/document/<int:doc_id>/information_sources', methods=['GET'])
def document_information_sources(doc_id: int):
    """Return structured provenance links for a document."""
    from sqlalchemy import select
    from library.db.models import DocumentInformationSource

    session = get_scoped_session()
    if session.get(Document, doc_id) is None:
        return {"status": "error", "message": "Document not found"}, 404
    links = session.scalars(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc_id
    ).order_by(DocumentInformationSource.role, DocumentInformationSource.id)).all()
    from library.db.models import DocumentSourceRelationship
    approved_relationships = session.scalars(select(DocumentSourceRelationship).where(
        DocumentSourceRelationship.document_id == doc_id,
        DocumentSourceRelationship.status == "approved",
    )).all()
    links = _display_information_source_links(links, approved_relationships)
    entries = [{
        "id": link.id,
        "source_id": link.source_id,
        "canonical_name": link.source.canonical_name,
        "source_type": link.source.source_type,
        "domain": link.source.domain,
        "role": link.role,
        "raw_mention": link.raw_mention,
        "source_url": link.source_url,
        "evidence_excerpt": link.evidence_excerpt,
        "confidence": link.confidence,
        "extraction_method": link.extraction_method,
        "review_status": link.review_status,
    } for link in links]
    return {"status": "success", "count": len(entries), "entries": entries}, 200


def _display_information_source_links(links, approved_relationships):
    """Choose one direct-provenance row per source for reader and graph.

    A source can be found by overlapping extractors.  Showing every row makes
    AFP/France24 appear twice.  More importantly, a weak NER "cited" row for
    the author of a statement must yield to a reviewer-approved chain such as
    ``EDF --issued_statement--> AFP``.
    """
    relation_subjects = {
        relation.subject_name.casefold()
        for relation in approved_relationships
        if relation.predicate == "issued_statement"
    }
    role_priority = {
        "publisher": 0,
        "original_reporting": 1,
        "republication": 2,
        "data_source": 3,
        "cited": 4,
    }
    selected = {}
    for link in links:
        source = link.source
        # This is the known false-positive shape fixed in
        # extract_ner_cited_sources(). Keep the stored record/audit intact,
        # but do not present it as a direct portal source.
        if (link.role == "cited"
                and getattr(link, "extraction_method", None) == "ner_context_rule"
                and source.canonical_name.casefold() in relation_subjects):
            continue
        key = source.id
        previous = selected.get(key)
        if previous is None or role_priority.get(link.role, 99) < role_priority.get(previous.role, 99):
            selected[key] = link
    return sorted(selected.values(), key=lambda link: (role_priority.get(link.role, 99), link.id))


@app.route('/document/<int:doc_id>/information_sources/<int:link_id>/approve', methods=['POST'])
def approve_document_information_source(doc_id: int, link_id: int):
    """Explicitly protect one provenance link from automatic refreshes."""
    from library.db.models import DocumentInformationSource

    session = get_scoped_session()
    link = session.get(DocumentInformationSource, link_id)
    if link is None or link.document_id != doc_id:
        return {"status": "error", "message": "Information source link not found"}, 404
    link.review_status = "approved"
    session.commit()
    return {"status": "success", "id": link.id, "review_status": link.review_status}, 200


@app.route('/document/<int:doc_id>/organizations/<int:link_id>/approve', methods=['POST'])
def approve_document_organization(doc_id: int, link_id: int):
    """Explicitly protect one document-organization link from NER refreshes."""
    from library.db.models import DocumentOrganization

    session = get_scoped_session()
    link = session.get(DocumentOrganization, link_id)
    if link is None or link.document_id != doc_id:
        return {"status": "error", "message": "Organization link not found"}, 404
    link.review_status = "approved"
    session.commit()
    return {"status": "success", "id": link.id, "review_status": link.review_status}, 200


@app.route('/document/<int:doc_id>/cited_publications', methods=['GET', 'POST'])
def document_cited_publications(doc_id: int):
    """List citations or refresh them from the latest reviewed chunk text."""
    from sqlalchemy import select
    from library.db.models import (
        CitedPublication, DocumentAnalysisRun, DocumentChunk, DocumentCitedPublication,
    )

    session = get_scoped_session()
    doc = session.get(Document, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        chunk_ids = data.get("chunk_ids")
        replace_document = True
        if chunk_ids is not None:
            if not isinstance(chunk_ids, list) or not chunk_ids or not all(isinstance(value, int) for value in chunk_ids):
                return {"status": "error", "message": "chunk_ids must be a non-empty list of integers"}, 400
            wanted = set(chunk_ids)
            selected_chunks = session.scalars(select(DocumentChunk).where(
                DocumentChunk.document_id == doc_id, DocumentChunk.id.in_(wanted),
            ).order_by(DocumentChunk.position)).all()
            if len(selected_chunks) != len(wanted):
                return {"status": "error", "message": "One or more chunks do not belong to this document"}, 400
            replace_document = False
        else:
            run = session.scalar(select(DocumentAnalysisRun).where(
                DocumentAnalysisRun.document_id == doc_id
            ).order_by(DocumentAnalysisRun.created_at.desc()))
            if run is None:
                return {"status": "error", "message": "Document has no analysis run"}, 400
            selected_chunks = list(run.chunks)
        try:
            from library.cited_publications import refresh_document_cited_publications
            result = refresh_document_cited_publications(
                session, doc_id, selected_chunks, replace_document=replace_document,
            )
            session.commit()
        except Exception:
            session.rollback()
            logging.exception("cited publication refresh failed for document %s", doc_id)
            return {"status": "error", "message": "Citation refresh failed"}, 500

    rows = session.execute(select(DocumentCitedPublication, CitedPublication).join(
        CitedPublication, CitedPublication.id == DocumentCitedPublication.publication_id
    ).where(DocumentCitedPublication.document_id == doc_id).order_by(
        DocumentCitedPublication.id
    )).all()
    entries = [{
        "id": link.id, "publication_id": publication.id,
        "title": publication.title, "journal": publication.journal,
        "publication_year": publication.publication_year,
        "doi": publication.doi, "pmid": publication.pmid, "pmcid": publication.pmcid,
        "canonical_url": publication.canonical_url, "chunk_id": link.chunk_id,
        "raw_citation": link.raw_citation, "evidence_excerpt": link.evidence_excerpt,
        "review_status": link.review_status,
    } for link, publication in rows]
    response = {"status": "success", "count": len(entries), "entries": entries}
    if request.method == 'POST':
        response["refreshed_count"] = len(result["publications"])
        response["scanned_chunk_ids"] = [chunk.id for chunk in selected_chunks]
    return response, 200


@app.route('/document/<int:doc_id>/relationship_graph', methods=['GET'])
def document_relationship_graph(doc_id: int):
    """Return the stored provenance and organization relations of one document.

    The graph is deliberately assembled on the server: its edges mirror foreign
    keys and document links, rather than asking the reader to infer relations
    from matching display names.
    """
    from sqlalchemy import or_, select
    from library.db.models import (
        CitedPublication, DocumentCitedPublication, DocumentInformationSource,
        DocumentOrganization, DocumentSourceRelationship, Organization,
    )

    session = get_scoped_session()
    doc = session.get(Document, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    nodes = []
    edges = []
    node_ids = set()
    provenance_parent_node_id = (
        f"publisher:{doc.publisher.id}" if doc.publisher is not None else None
    )

    def add_node(node: dict):
        if node["id"] not in node_ids:
            nodes.append(node)
            node_ids.add(node["id"])

    if doc.publisher is not None:
        add_node({"id": provenance_parent_node_id, "type": "publisher",
                  "label": doc.publisher.canonical_name,
                  "href": f"/list?q={doc.publisher.canonical_name}"})

    approved_relationships = session.scalars(select(DocumentSourceRelationship).where(
        DocumentSourceRelationship.document_id == doc_id,
        DocumentSourceRelationship.status == "approved",
    )).all()
    information_links = session.scalars(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc_id,
    ).order_by(DocumentInformationSource.role, DocumentInformationSource.id)).all()
    information_links = _display_information_source_links(information_links, approved_relationships)
    has_rendered_publisher = False
    for link in information_links:
        source = link.source
        # The document publisher registry owns canonical domain grouping.  A
        # provenance row may carry the imported hostname (wiadomosci.wp.pl),
        # while the publisher is the registrable-domain entity (wp.pl).
        if link.role == "publisher" and doc.publisher is not None:
            publisher = doc.publisher
            publisher_node_id = f"publisher:{publisher.id}"
            add_node({
                "id": publisher_node_id, "type": "publisher",
                "label": publisher.canonical_name,
                "href": f"/list?q={publisher.canonical_name}",
                "external_url": link.source_url,
            })
            has_rendered_publisher = True
            continue
        # A source that is normalized to an Organization is the same real-world
        # entity. Render one organization node instead of visually duplicating
        # names such as EDF or AFP; the provenance role stays on the edge.
        organization = source.organization if source.organization_id is not None else None
        if organization is not None:
            source_node_id = f"organization:{organization.id}"
            add_node({
                "id": source_node_id, "type": "organization",
                "label": organization.canonical_name,
                "href": f"/information-sources?id={source.id}",
                "external_url": link.source_url,
                "linked_to_source": True,
                "description": organization.description,
            })
        else:
            source_node_id = f"information_source:{source.id}"
            source_type = "publisher" if link.role == "publisher" else "information_source"
            add_node({
                "id": source_node_id, "type": source_type,
                "label": source.canonical_name,
                "href": f"/information-sources?id={source.id}",
                "external_url": link.source_url,
            })
        if provenance_parent_node_id is not None:
            edges.append({"id": f"provenance:{link.id}", "source": provenance_parent_node_id,
                          "target": source_node_id, "type": link.role})

    # A publisher registry entry is the fallback when provenance analysis did
    # not produce a publisher role; do not create a second publisher node.
    if not has_rendered_publisher and doc.publisher is not None:
        publisher = doc.publisher
        publisher_node_id = f"publisher:{publisher.id}"
        add_node({
            "id": publisher_node_id, "type": "publisher",
            "label": publisher.canonical_name,
            "href": f"/list?q={publisher.canonical_name}",
        })

    publication_rows = session.execute(select(DocumentCitedPublication, CitedPublication).join(
        CitedPublication, CitedPublication.id == DocumentCitedPublication.publication_id,
    ).where(DocumentCitedPublication.document_id == doc_id).order_by(
        DocumentCitedPublication.id,
    )).all()
    for link, publication in publication_rows:
        publication_node_id = f"cited_publication:{publication.id}"
        identifier = publication.doi or publication.pmid or publication.pmcid or "Publikacja"
        add_node({
            "id": publication_node_id, "type": "cited_publication",
            "label": publication.title or identifier,
            "external_url": publication.canonical_url,
        })
        if provenance_parent_node_id is not None:
            edges.append({"id": f"citation:{link.id}", "source": provenance_parent_node_id,
                          "target": publication_node_id, "type": "cited_publication"})

    # Mentioned organizations remain visible as unconnected context nodes. A
    # line to the portal would falsely imply a source/citation relationship.
    for _link, organization in session.execute(select(DocumentOrganization, Organization).join(
        Organization, Organization.id == DocumentOrganization.organization_id,
    ).where(DocumentOrganization.document_id == doc_id)).all():
        add_node({"id": f"organization:{organization.id}", "type": "organization",
                  "label": organization.canonical_name,
                  "href": f"/list?q={organization.canonical_name}", "context_only": True,
                  "description": organization.description})
    # Reviewer-approved claim provenance.  Resolve against graph labels first
    # to reuse organization/source nodes; retain a named node for a relation
    # whose entity has not otherwise been extracted yet.
    label_to_node = {node["label"].casefold(): node["id"] for node in nodes}
    for relation in approved_relationships:
        def relation_node(name):
            key = name.casefold()
            node_id = label_to_node.get(key)
            if node_id is None:
                node_id = f"relationship_entity:{relation.id}:{key}"
                add_node({"id": node_id, "type": "information_source", "label": name})
                label_to_node[key] = node_id
            return node_id
        edges.append({
            "id": f"source_relationship:{relation.id}",
            "source": relation_node(relation.subject_name),
            "target": relation_node(relation.object_name),
            "type": relation.predicate,
            "evidence_excerpt": relation.evidence_excerpt,
            "confidence": relation.confidence,
        })

    # Confirmed document-to-document links (library/document_links_service.py).
    # These connect two Document nodes directly rather than the entity graph
    # above, so a reader immediately sees "this post discusses that repo".
    from library.db.models import DocumentLink
    from library.document_links_service import RELATIONS as _LINK_RELATIONS

    document_links = session.scalars(select(DocumentLink).where(
        DocumentLink.status == "confirmed",
        or_(DocumentLink.from_document_id == doc_id, DocumentLink.to_document_id == doc_id),
    )).all()
    for link in document_links:
        for endpoint in (link.from_document, link.to_document):
            if endpoint is None:
                continue
            node_id = f"document:{endpoint.id}"
            add_node({
                "id": node_id,
                "type": "document",
                "label": endpoint.title or endpoint.url,
                "href": f"/read/{endpoint.id}",
                "external_url": endpoint.url,
                "is_self": endpoint.id == doc_id,
            })
        forward_label = _LINK_RELATIONS.get(link.relation, (link.relation, link.relation))[0]
        edges.append({
            "id": f"document_link:{link.id}",
            "source": f"document:{link.from_document_id}",
            "target": f"document:{link.to_document_id}",
            "type": forward_label,
            "relation": link.relation,
        })

    return {"status": "success", "nodes": nodes, "edges": edges}, 200


def _decide_person_link(link_id: int, require_review: bool):
    """Shared handler for person-link decisions (approve/reject/merge).

    require_review=True is the /persons_review queue semantics (409 outside
    the queue); False is the editor path — lets the user undo a wrong
    wikidata/alias match on any link.
    """
    from library import person_registry
    from library.entity_review_audit import record_entity_decision
    from library.db.models import DocumentPerson, Person

    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ("approve", "reject", "merge"):
        return {"status": "error", "message": "action must be one of: approve, reject, merge"}, 400

    session = get_scoped_session()
    link = session.get(DocumentPerson, link_id)
    if link is None:
        return {"status": "error", "message": "Review entry not found"}, 404
    if require_review and link.confidence != person_registry.CONFIDENCE_MANUAL_REVIEW:
        return {"status": "error", "message": "Entry is not awaiting review"}, 409

    audit_snapshot = {
        "document_id": link.document_id,
        "document_person_id": link.id,
        "person_id": link.person_id,
        "entity_type": "persName",
        "entity_text": link.raw_mention,
        "original_confidence": link.confidence,
        "source_excerpt": link.source_excerpt,
        "details": {"role": link.role, "review_queue": require_review},
    }
    try:
        if action == "approve":
            result = person_registry.approve_review_link(session, link)
            decision = "confirmed"
        elif action == "reject":
            result = person_registry.reject_review_link(session, link)
            decision = "rejected"
        else:
            target_id, error = _entities_doc_id(data.get('target_person_id'))
            if error:
                return error
            target = session.get(Person, target_id)
            if target is None:
                return {"status": "error", "message": "Target person not found"}, 404
            result = person_registry.merge_review_link(session, link, target)
            decision = "corrected"
        record_entity_decision(
            session,
            **audit_snapshot,
            decision=decision,
            reason_code=(data.get("reason_code") or "").strip() or None,
            comment=(data.get("comment") or "").strip() or None,
            replacement_person_id=result.get("person_id") if action == "merge" else None,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}, 400
    except Exception:
        session.rollback()
        logging.exception("person link decision failed for link %s", link_id)
        return {"status": "error", "message": "DB error"}, 500

    return {"status": "success", **result}, 200


@app.route('/persons_review/<int:link_id>', methods=['PATCH', 'OPTIONS'])
def persons_review_decide(link_id: int):
    """Decide a manual_review entry. Body (JSON): {"action": "approve"|"reject"|"merge",
    "target_person_id": <id>} — target_person_id only for merge."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200
    return _decide_person_link(link_id, require_review=True)


@app.route('/document_persons/<int:link_id>', methods=['PATCH', 'OPTIONS'])
def document_persons_decide(link_id: int):
    """Decide any document<->person link, regardless of confidence (editor UI).

    Same actions/body as /persons_review — used to undo wrong
    wikidata_matched/alias_matched links (e.g. an STT-garbled mention
    resolved to the wrong person)."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200
    return _decide_person_link(link_id, require_review=False)


@app.route('/persons/<int:person_id>/aliases', methods=['POST', 'OPTIONS'])
def person_alias_add(person_id: int):
    """Manually add an alias (e.g. a podcast nickname) to a person.

    Body (JSON or form): {"alias": "..."}. The next NER run resolves the
    alias via alias_matched without Wikidata or review."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import Person
    from library.person_registry import add_person_alias

    data = request.get_json(silent=True) or {}
    alias = (data.get('alias') or request.form.get('alias') or "").strip()
    if not alias:
        return {"status": "error", "message": "alias is required"}, 400

    session = get_scoped_session()
    person = session.get(Person, person_id)
    if person is None:
        return {"status": "error", "message": "Person not found"}, 404

    try:
        added = add_person_alias(session, person, alias)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("alias add failed for person %s", person_id)
        return {"status": "error", "message": "DB error"}, 500

    # jsonify enforces Content-Type: application/json (CodeQL py/reflective-xss)
    return jsonify({"status": "success", "person_id": person_id, "added": added,
                    "aliases": [a.alias for a in person.aliases]}), 200


@app.route('/website_entities/<int:entity_id>/relevance', methods=['PATCH'])
def website_entities_relevance(entity_id: int):
    """Set manual relevance without preventing NER from replacing the entity."""
    from library.db.models import DocumentEntity
    from library.entity_service import get_document_entities
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES, add_place_tag, remove_orphaned_tag

    data = request.get_json(silent=True)
    relevance = data.get("relevance") if isinstance(data, dict) else None
    if relevance not in ("central", "related", "figurative"):
        return jsonify(status="error", message="Invalid relevance: expected central, related or figurative."), 400
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Entity not found."), 404
    try:
        entity.relevance = relevance
        if entity.entity_type in PLACE_ENTITY_TYPES:
            document = session.get(Document, entity.document_id)
            if document is not None:
                if relevance == "figurative":
                    remove_orphaned_tag(session, document, entity)
                else:
                    add_place_tag(document, entity)
        record_entity_decision(
            session, document_id=entity.document_id, document_entity_id=entity.id,
            entity_type=entity.entity_type, entity_text=entity.entity_text, decision="relevance_set",
            details={"relevance": relevance, "variants": list(entity.variants or [])},
        )
        session.flush()
        item = next(item for item in get_document_entities(session, entity.document_id)[entity.entity_type]
                    if item["id"] == entity.id)
        item.update(entity_type=entity.entity_type, mention_count=entity.mention_count)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Entity relevance update failed for entity %s", entity_id)
        return jsonify(status="error", message="Could not save entity relevance."), 500
    return jsonify(status="success", entity=item), 200


@app.route('/website_entities/<int:entity_id>', methods=['PATCH'])
def website_entities_rename(entity_id: int):
    """Correct a place name while retaining its original chapter-matching forms."""
    from sqlalchemy.exc import IntegrityError
    from library.db.models import DocumentEntity
    from library.entity_service import get_document_entities
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES, geocode_single_place, remove_orphaned_tag

    data = request.get_json(silent=True)
    name = data.get("text") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 500:
        return jsonify(status="error", message="Nazwa musi zawierać od 1 do 500 znaków."), 400
    name = name.strip()
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in PLACE_ENTITY_TYPES:
        return jsonify(status="error", message="Można poprawiać tylko nazwy miejsc."), 400

    conflict_message = 'Takie miejsce już istnieje. Wybierz „Połącz z innym miejscem”.'

    def conflict_response(duplicate):
        return jsonify(status="error", message=conflict_message, conflict_entity={
            "id": duplicate.id, "text": duplicate.entity_text, "entity_type": duplicate.entity_type,
        } if duplicate is not None else None), 409

    try:
        duplicate = session.query(DocumentEntity).filter(
            DocumentEntity.document_id == entity.document_id,
            DocumentEntity.entity_type == entity.entity_type,
            DocumentEntity.entity_text == name,
            DocumentEntity.id != entity.id,
        ).first()
        if duplicate is not None:
            return conflict_response(duplicate)
        old_name = entity.entity_text
        old_variants = list(entity.variants or [])
        document = session.get(Document, entity.document_id)
        removed_tag = remove_orphaned_tag(session, document, entity) if document is not None else None
        entity.entity_text = name
        entity.variants = list(dict.fromkeys([*old_variants, old_name, name]))
        entity.source = "manual"
        entity.geocode = None
        entity.geocode_id = None
        record_entity_decision(
            session, document_id=entity.document_id, document_entity_id=entity.id,
            entity_type=entity.entity_type, entity_text=old_name, decision="renamed",
            details={"new_text": name, "variants": old_variants, "removed_tag": removed_tag},
        )
        session.flush()
        geocoding = geocode_single_place(session, document, entity)
        session.flush()
        item = next(item for item in get_document_entities(session, entity.document_id)[entity.entity_type]
                    if item["id"] == entity.id)
        item.update(entity_type=entity.entity_type, mention_count=entity.mention_count)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if getattr(exc.orig, "pgcode", None) == "23505":
            duplicate = session.query(DocumentEntity).filter(
                DocumentEntity.document_id == entity.document_id,
                DocumentEntity.entity_type == entity.entity_type,
                DocumentEntity.entity_text == name,
                DocumentEntity.id != entity.id,
            ).first()
            return conflict_response(duplicate)
        logging.exception("entity rename failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się zapisać nazwy miejsca."), 500
    except Exception:
        session.rollback()
        logging.exception("entity rename failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się zapisać nazwy miejsca."), 500
    return jsonify(status="success", entity=item, **geocoding), 200


@app.route('/website_entities/<int:entity_id>/confirm_place', methods=['POST'])
def website_entities_confirm_place(entity_id: int):
    """Approve a displayed geocoder proposal and durably record the selection."""
    from library.db.models import DocumentEntity, GeocodeCache
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES, geocode_single_place, remove_orphaned_tag

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(status="error", message="Nieprawidłowe dane."), 400
    selected_id = data.get("selected_geocode_id")
    if selected_id is not None and (type(selected_id) is not int or selected_id <= 0):
        return jsonify(status="error", message="Nieprawidłowy identyfikator lokalizacji."), 400
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in PLACE_ENTITY_TYPES:
        return jsonify(status="error", message="Encja nie jest miejscem."), 400
    proposal = session.get(GeocodeCache, selected_id) if selected_id is not None else entity.geocode
    if proposal is None or not proposal.resolved or proposal.lat is None or proposal.lon is None:
        return jsonify(status="error", message="Brak propozycji lokalizacji."), 409
    try:
        document = session.get(Document, entity.document_id)
        if document is not None and entity.geocode is not None and entity.geocode.id != proposal.id:
            remove_orphaned_tag(session, document, entity)
        entity.place_verification_status = "confirmed"
        entity.place_review_reason = None
        entity.source = "manual"
        geocode_single_place(session, document, entity, selected_geocode=proposal)
        record_entity_decision(
            session, document_id=entity.document_id, document_entity_id=entity.id,
            entity_type=entity.entity_type, entity_text=entity.entity_text, decision="place_confirmed",
            details={"name": entity.entity_text, "variants": list(entity.variants or []),
                     "geocode_id": proposal.id, "display_name": proposal.display_name},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Place confirmation failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się zatwierdzić lokalizacji."), 500
    return jsonify(status="success"), 200


@app.route('/website_entities/<int:entity_id>/reject_place', methods=['POST'])
def website_entities_reject_place(entity_id: int):
    """Dismiss a geocoder proposal held at ``needs_review``: the place stays unlocated, without a tag."""
    from library.db.models import DocumentEntity
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES

    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in PLACE_ENTITY_TYPES:
        return jsonify(status="error", message="Encja nie jest miejscem."), 400
    if entity.place_verification_status != "needs_review":
        return jsonify(status="error", message="Miejsce nie czeka na potwierdzenie."), 409
    try:
        proposal = entity.geocode
        entity.place_verification_status = "rejected"
        entity.place_review_reason = "rejected_by_user"
        entity.source = "manual"
        record_entity_decision(
            session, document_id=entity.document_id, document_entity_id=entity.id,
            entity_type=entity.entity_type, entity_text=entity.entity_text, decision="place_rejected",
            details={"name": entity.entity_text, "variants": list(entity.variants or []),
                     "geocode_id": proposal.id if proposal is not None else None},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Place proposal rejection failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się odrzucić propozycji."), 500
    return jsonify(status="success"), 200


@app.route('/website_entities/<int:entity_id>/to_organization', methods=['POST'])
def website_entities_to_organization(entity_id: int):
    """Retype a place or person entity as an organization (NER mislabelled it, e.g. "Huti").

    Optional body {"text": "X"} names the organization (a person entity "Xie" is the speech-to-text
    form of "X"); the mention stays a surface form. A person's document link is dropped like on a
    deletion and the decision is audited as ``person_to_organization`` and replayed after refreshes.
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.db.models import DocumentEntity, DocumentPerson
    from library.entity_overrides import convert_place_to_organization
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES, remove_orphaned_tag

    data = request.get_json(silent=True) or {}
    new_text = data.get('text')
    if new_text is not None and (not isinstance(new_text, str) or not new_text.strip() or len(new_text) > 500):
        return jsonify(status="error", message="Nieprawidłowa nazwa organizacji."), 400
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    from_person = entity.entity_type == "persName"
    if not from_person and entity.entity_type not in PLACE_ENTITY_TYPES:
        return jsonify(status="error", message="Encja nie jest miejscem ani osobą."), 400
    try:
        document = session.get(Document, entity.document_id)
        old_text, old_type, old_variants = entity.entity_text, entity.entity_type, list(entity.variants or [])
        removed_tag = None
        if from_person:
            link = session.execute(sa_select(DocumentPerson).where(
                DocumentPerson.document_id == entity.document_id,
                sa_func.lower(DocumentPerson.raw_mention) == old_text.lower(),
            )).scalars().first()
            if link is not None:
                person_registry.reject_review_link(session, link)
        elif document is not None:
            removed_tag = remove_orphaned_tag(session, document, entity)
        record_entity_decision(
            session, document_id=entity.document_id, document_entity_id=entity.id,
            entity_type=old_type, entity_text=old_text,
            decision="person_to_organization" if from_person else "place_to_organization",
            details={"variants": old_variants, "removed_tag": removed_tag,
                     **({"new_text": new_text.strip()} if new_text else {})},
        )
        new_entity, organization = convert_place_to_organization(session, entity, new_text=new_text)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Entity to organization conversion failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się zmienić encji na organizację."), 500
    return jsonify(status="success", entity_id=new_entity.id, organization_id=organization.id,
                   organization_name=organization.canonical_name, removed_tag=removed_tag), 200


@app.route('/website_entities/<int:entity_id>/to_place', methods=['POST'])
def website_entities_to_place(entity_id: int):
    """Retype a person or organization entity as a place (NER mislabelled it, e.g. "Kandaharem",
    "Tela Avivwu").

    Optional body {"text": "Kandahar"} names the place (default: the mention as stored). The person's
    document link (or the organization's link, the organization itself stays in the registry) is dropped
    like on a deletion, the place is geocoded once through the cache (a country gets its ``kraj-*`` tag
    instead) and the decision is audited as ``person_to_place`` / ``organization_to_place`` and replayed
    after entity refreshes (library/entity_overrides.py).
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.country_gazetteer import country_tag_for
    from library.db.models import DocumentEntity, DocumentPerson
    from library.entity_overrides import convert_person_to_place
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import geocode_single_place

    data = request.get_json(silent=True) or {}
    new_text = data.get('text')
    if new_text is not None and (not isinstance(new_text, str) or not new_text.strip() or len(new_text) > 500):
        return jsonify(status="error", message="Nieprawidłowa nazwa miejsca."), 400
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in ("persName", "orgName"):
        return jsonify(status="error", message="Encja nie jest osobą ani organizacją."), 400
    from_organization = entity.entity_type == "orgName"
    try:
        document = session.get(Document, entity.document_id)
        old_text, old_variants = entity.entity_text, list(entity.variants or [])
        if from_organization:
            from library.entity_overrides import drop_organization_links
            link = link_result = None
            drop_organization_links(session, entity)
        else:
            link = session.execute(sa_select(DocumentPerson).where(
                DocumentPerson.document_id == entity.document_id,
                sa_func.lower(DocumentPerson.raw_mention) == old_text.lower(),
            )).scalars().first()
            link_result = person_registry.reject_review_link(session, link) if link is not None else None
        place = convert_person_to_place(session, entity, new_text)
        tag = country_tag_for(place.entity_text)
        if tag is not None and document is not None:
            existing = [t.strip() for t in (document.tags or "").split(",") if t.strip()]
            if tag not in existing:
                document.tags = ",".join([*existing, tag])
        elif place.geocode_id is None and document is not None:
            geocode_single_place(session, document, place)
        record_entity_decision(
            session, document_id=place.document_id, document_entity_id=place.id,
            document_person_id=getattr(link, "id", None), person_id=getattr(link, "person_id", None),
            entity_type="orgName" if from_organization else "persName", entity_text=old_text,
            decision="organization_to_place" if from_organization else "person_to_place",
            details={"new_text": place.entity_text, "variants": old_variants},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Entity to place conversion failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się zmienić encji na miejsce."), 500
    return jsonify(status="success", entity_id=place.id, place_name=place.entity_text,
                   person_deleted=bool(link_result and link_result.get("person_deleted"))), 200


@app.route('/website_entities/<int:entity_id>/to_person', methods=['POST'])
def website_entities_to_person(entity_id: int):
    """Retype an organization or place entity as a person (NER mislabelled it).

    The organization's document link is dropped (the organization stays in the registry; a place loses its
    orphaned ``miejsce-*`` tag and is audited as ``place_to_person``), a
    ``source='manual'`` persName row replaces the entity and the mention is resolved through the person
    registry (Wikidata + context LLM; a failure of that lookup keeps the conversion). Audited as
    ``organization_to_person`` and replayed after entity refreshes (library/entity_overrides.py).
    """
    from library import person_registry
    from library.db.models import DocumentEntity
    from library.entity_overrides import convert_entity_to_person, drop_organization_links
    from library.entity_review_audit import record_entity_decision

    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    from library.place_verification import PLACE_ENTITY_TYPES, remove_orphaned_tag

    from_place = entity.entity_type in PLACE_ENTITY_TYPES
    if entity.entity_type != "orgName" and not from_place:
        return jsonify(status="error", message="Encja nie jest organizacją ani miejscem."), 400
    old_text, old_type, old_variants = entity.entity_text, entity.entity_type, list(entity.variants or [])
    try:
        document = session.get(Document, entity.document_id)
        removed_tag = None
        if from_place:
            removed_tag = remove_orphaned_tag(session, document, entity) if document is not None else None
        else:
            drop_organization_links(session, entity)
        person_entity = convert_entity_to_person(session, entity)
        record_entity_decision(
            session, document_id=person_entity.document_id, document_entity_id=person_entity.id,
            entity_type=old_type, entity_text=old_text,
            decision="place_to_person" if from_place else "organization_to_person",
            details={"variants": old_variants, "removed_tag": removed_tag},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Organization to person conversion failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się zmienić organizacji na osobę."), 500
    resolved = None
    try:
        if document is not None:
            resolved = person_registry.resolve_document_persons(
                session, document, document.text_md or document.text or "", only_names=[person_entity.entity_text],
            )
            session.commit()
    except Exception:
        session.rollback()
        logging.exception("Person resolution after organization conversion failed for entity %s", entity_id)
    return jsonify(status="success", entity_id=person_entity.id, person_name=person_entity.entity_text,
                   linked=[canonical for _name, canonical, _conf in (resolved or {}).get("linked", [])]), 200


@app.route('/website_entities/<int:entity_id>/to_product', methods=['POST'])
def website_entities_to_product(entity_id: int):
    """Retype a person, organization or place entity as a product/system (NER mislabelled it, e.g. "Starshield").

    Optional body {"text": "Starshield", "entity_type": "productName"|"eventName"} names the product (default:
    the mention as stored) and picks product (default) or named event. A person's
    document link, an organization's link (it stays in the registry) or a place's orphaned tag is dropped
    like on a deletion; the row becomes a ``source='manual'`` productName. Audited as ``entity_to_product``
    and replayed after entity refreshes (library/entity_overrides.py).
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.db.models import DocumentEntity, DocumentPerson
    from library.entity_overrides import convert_entity_to_product, drop_organization_links
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES, remove_orphaned_tag

    data = request.get_json(silent=True) or {}
    new_text = data.get('text')
    target_type = data.get('entity_type') or "productName"
    if target_type not in ("productName", "eventName"):
        return jsonify(status="error", message="entity_type musi być productName lub eventName."), 400
    if new_text is not None and (not isinstance(new_text, str) or not new_text.strip() or len(new_text) > 500):
        return jsonify(status="error", message="Nieprawidłowa nazwa."), 400
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in ("persName", "orgName", *PLACE_ENTITY_TYPES):
        return jsonify(status="error", message="Encja nie jest osobą, organizacją ani miejscem."), 400
    try:
        document = session.get(Document, entity.document_id)
        old_text, old_type, old_variants = entity.entity_text, entity.entity_type, list(entity.variants or [])
        removed_tag = None
        if old_type == "persName":
            link = session.execute(sa_select(DocumentPerson).where(
                DocumentPerson.document_id == entity.document_id,
                sa_func.lower(DocumentPerson.raw_mention) == old_text.lower(),
            )).scalars().first()
            if link is not None:
                person_registry.reject_review_link(session, link)
        elif old_type == "orgName":
            drop_organization_links(session, entity)
        elif document is not None:
            removed_tag = remove_orphaned_tag(session, document, entity)
        product = convert_entity_to_product(session, entity, new_text, target_type=target_type)
        record_entity_decision(
            session, document_id=product.document_id, document_entity_id=product.id,
            entity_type=old_type, entity_text=old_text, decision="entity_to_product",
            details={"variants": old_variants, "removed_tag": removed_tag, "new_text": product.entity_text,
                     "target_type": target_type},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Entity to product conversion failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się zmienić encji na produkt / system."), 500
    return jsonify(status="success", entity_id=product.id, product_name=product.entity_text,
                   removed_tag=removed_tag), 200


@app.route('/website_entities/<int:entity_id>/from_product', methods=['POST'])
def website_entities_from_product(entity_id: int):
    """Turn a product/system (or named event) entity into another type (marked by mistake).

    Body: {"entity_type": "persName"|"orgName"|"placeName"|"productName"|"eventName", "text": "Kandahar"?}; an
    event's approved description is not carried over. The source row is removed
    and the mention is added like a hand-selected one (``add_manual_entity``): an organization is resolved
    through the registry, a place geocoded once (a country gets its ``kraj-*`` tag), a person through the
    person registry; counts and surface forms are kept. Audited as ``product_to_entity`` (so a replayed
    ``entity_added``/``entity_to_product`` of the product does not bring it back) plus ``entity_added`` for
    the new row (library/entity_overrides.py).
    """
    from library import person_registry
    from library.country_gazetteer import country_tag_for
    from library.db.models import DocumentEntity
    from library.entity_overrides import add_manual_entity
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import geocode_single_place

    data = request.get_json(silent=True) or {}
    entity_type, new_text = data.get('entity_type'), data.get('text')
    if entity_type not in ("persName", "orgName", "placeName", "productName", "eventName"):
        return jsonify(status="error", message="entity_type musi być persName, orgName, placeName, "
                       "productName lub eventName."), 400
    if new_text is not None and (not isinstance(new_text, str) or not new_text.strip() or len(new_text) > 200):
        return jsonify(status="error", message="Nieprawidłowa nazwa."), 400
    session = get_scoped_session()
    product = session.get(DocumentEntity, entity_id)
    if product is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if product.entity_type not in ("productName", "eventName"):
        return jsonify(status="error", message="Encja nie jest produktem / systemem ani wydarzeniem."), 400
    if entity_type == product.entity_type:
        return jsonify(status="error", message="Encja już ma ten typ."), 400
    source_type = product.entity_type
    doc_id = product.document_id
    document = session.get(Document, doc_id)
    old_text, old_variants, count = product.entity_text, list(product.variants or []), product.mention_count or 1
    name = " ".join(new_text.split()) if new_text else None
    try:
        session.delete(product)
        session.flush()
        row, organization = add_manual_entity(session, doc_id, entity_type, old_text, name, count)
        row.variants = [v for v in dict.fromkeys([*(row.variants or []), *old_variants])
                        if v.casefold() != row.entity_text.casefold()]
        if entity_type == "placeName" and document is not None:
            tag = country_tag_for(row.entity_text)
            if tag is not None:
                existing_tags = [t.strip() for t in (document.tags or "").split(",") if t.strip()]
                if tag not in existing_tags:
                    document.tags = ",".join([*existing_tags, tag])
            elif row.geocode_id is None:
                geocode_single_place(session, document, row)
        record_entity_decision(
            session, document_id=doc_id, document_entity_id=row.id, entity_type=source_type,
            entity_text=old_text, decision="product_to_entity",
            details={"target_type": entity_type, "new_text": row.entity_text, "variants": old_variants},
        )
        record_entity_decision(
            session, document_id=doc_id, document_entity_id=row.id, entity_type=entity_type,
            entity_text=row.entity_text, decision="entity_added",
            details={"surface": old_text, "name": row.entity_text, "count": count},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Product to %s conversion failed for entity %s", entity_type, entity_id)
        return jsonify(status="error", message="Nie udało się zmienić produktu na wybrany typ."), 500
    linked = []
    if entity_type == "persName" and document is not None:
        try:
            resolved = person_registry.resolve_document_persons(
                session, document, document.text_md or document.text or "", only_names=[row.entity_text])
            session.commit()
            linked = [canonical for _name, canonical, _conf in (resolved or {}).get("linked", [])]
        except Exception:
            session.rollback()
            logging.exception("Person resolution after product conversion failed for entity %s", entity_id)
    return jsonify(status="success", entity_id=row.id, entity_type=row.entity_type, entity_text=row.entity_text,
                   organization_id=getattr(organization, "id", None), linked=linked), 200


@app.route('/website_entities/<int:entity_id>/transcription_error', methods=['POST'])
def website_entities_transcription_error(entity_id: int):
    """Mark an entity as a speech-to-text slip of another entity of the same document ("Hutni" for "Huti").

    Body {"correct_name": "Huti"} names an entity that already exists in the document (any type). The wrong
    entity is removed WITHOUT touching the registry (a person link is dropped, no alias is created), its
    mentions and spelling become surface forms of the correct entity (counts added, text keeps highlighting)
    and, when the document has a channel (byline), the slip is added to the channel glossary so the next
    entity refresh repairs the text before NER. Audited as ``transcription_error`` and replayed.
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.db.models import DocumentEntity, DocumentPerson, NerChannelGlossaryEntry
    from library.entity_overrides import drop_organization_links
    from library.entity_review_audit import record_entity_decision
    from library.entity_service import PLACE_TYPES, merge_document_entities
    from library.place_verification import remove_orphaned_tag

    data = request.get_json(silent=True) or {}
    correct = data.get('correct_name')
    if not isinstance(correct, str) or not correct.strip() or len(correct) > 500:
        return jsonify(status="error", message="Nieprawidłowa poprawna nazwa."), 400
    correct = correct.strip()
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in ("persName", "orgName", *PLACE_TYPES):
        return jsonify(status="error", message="Ta encja nie może być błędem transkrypcji."), 400
    target = session.execute(sa_select(DocumentEntity).where(
        DocumentEntity.document_id == entity.document_id, DocumentEntity.id != entity.id,
        DocumentEntity.entity_type.in_(("persName", "orgName", *PLACE_TYPES)),
        sa_func.lower(DocumentEntity.entity_text) == correct.lower(),
    )).scalars().first()
    if target is None:
        return jsonify(status="error", message=f"W dokumencie nie ma encji „{correct}”. Najpierw zmień typ tej "
                       "encji na właściwy (Zmień na organizację / miejsce) i nadaj jej tę nazwę."), 404
    wrong, wrong_variants, wrong_type = entity.entity_text, list(entity.variants or []), entity.entity_type
    try:
        document = session.get(Document, entity.document_id)
        if wrong_type == "persName":
            link = session.execute(sa_select(DocumentPerson).where(
                DocumentPerson.document_id == entity.document_id,
                sa_func.lower(DocumentPerson.raw_mention) == wrong.lower(),
            )).scalars().first()
            if link is not None:
                person_registry.reject_review_link(session, link)
        elif wrong_type == "orgName":
            drop_organization_links(session, entity)
        elif document is not None:
            remove_orphaned_tag(session, document, entity)
        merge_document_entities(entity, target)
        session.delete(entity)
        glossary = False
        byline = ((document.byline if document is not None else None) or "").strip()
        if byline and len(wrong) >= 3:
            row = session.execute(sa_select(NerChannelGlossaryEntry).where(
                sa_func.lower(NerChannelGlossaryEntry.author) == byline.lower(),
                sa_func.lower(NerChannelGlossaryEntry.canonical_name) == target.entity_text.lower(),
            )).scalars().first()
            if row is None:
                session.add(NerChannelGlossaryEntry(author=byline, canonical_name=target.entity_text,
                                                    aliases=[wrong], fuzzy=False, created_by="ner-review"))
            elif wrong not in (row.aliases or []):
                row.aliases = [*(row.aliases or []), wrong]
            glossary = True
        session.flush()
        record_entity_decision(
            session, document_id=target.document_id, document_entity_id=target.id, entity_type=wrong_type,
            entity_text=wrong, decision="transcription_error",
            details={"target_entity_text": target.entity_text, "variants": wrong_variants},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Transcription error marking failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się oznaczyć błędu transkrypcji."), 500
    return jsonify(status="success", entity_id=target.id, entity_text=target.entity_text,
                   mention_count=target.mention_count, glossary=glossary), 200


@app.route('/website_entities/<int:entity_id>/real_name', methods=['POST'])
def website_entities_real_name(entity_id: int):
    """Give a person mention its real name (a nickname such as "Łacha Piachu" for Icchak Herzog).

    Body {"name": "Icchak Herzog"}. The name is looked up in the person registry (canonical name or alias);
    a missing person is created. The mention (and its surface forms) become aliases of that person, so later
    documents resolve it directly, and the document's link is pointed at the person (merging a previous
    link). The entity row and its text stay as they are, so the mentions keep highlighting.
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.db.models import DocumentEntity, DocumentPerson, Person

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 500:
        return jsonify(status="error", message="Nieprawidłowe nazwisko."), 400
    name = name.strip()
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type != "persName":
        return jsonify(status="error", message="Encja nie jest osobą."), 400
    try:
        person = person_registry.find_by_alias(session, name)
        created = person is None
        if created:
            person = Person(canonical_name=name)
            session.add(person)
            session.flush()
        for form in dict.fromkeys([entity.entity_text, *(entity.variants or [])]):
            person_registry.add_person_alias(session, person, form)
        link = session.execute(sa_select(DocumentPerson).where(
            DocumentPerson.document_id == entity.document_id,
            sa_func.lower(DocumentPerson.raw_mention) == entity.entity_text.lower(),
        )).scalars().first()
        if link is None:
            session.add(DocumentPerson(
                document_id=entity.document_id, person_id=person.id, raw_mention=entity.entity_text,
                confidence=person_registry.CONFIDENCE_MANUAL_CONFIRMED,
            ))
        elif link.person_id != person.id:
            person_registry.merge_review_link(session, link, person)
        else:
            link.confidence = person_registry.CONFIDENCE_MANUAL_CONFIRMED
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Real name assignment failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się nadać nazwiska."), 500
    return jsonify(status="success", person_id=person.id, canonical_name=person.canonical_name, created=created), 200


@app.route('/website_entities/<int:entity_id>/describe', methods=['POST'])
def website_entities_describe(entity_id: int):
    """Propose a description of an event or organization entity from the document text (not stored).

    Event: the sentences that mention it go to the tagging model (Bielik). Organization: the chapter that
    mentions it most often goes to the model. In both cases the model may use nothing else
    (library/event_description.py). Answers ``description`` (null when the text does not say enough) and
    the ``sentences`` used. An event description is stored by ``PUT /website_entities/<id>/description``,
    an organization one by ``PATCH /organizations/<id>`` once the reviewer approves or edits it.
    """
    from library.db.models import DocumentEntity
    from library.event_description import best_chapter, context_sentences, describe_event

    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in ("eventName", "orgName"):
        return jsonify(status="error", message="Opis można wygenerować tylko dla wydarzenia lub organizacji."), 400
    document = session.get(Document, entity.document_id)
    text = (document.text_md or document.text or "") if document is not None else ""
    forms = [entity.entity_text, *(entity.variants or [])]
    doc_title = getattr(document, "title", "") or ""
    if entity.entity_type == "orgName":
        from library.event_description import (
            MAX_CUSTOM_PROMPT_CHARS, build_organization_prompt, run_organization_description,
        )
        from library.llm_model_registry import is_selectable

        body = request.get_json(silent=True) or {}
        model = body.get('model')
        if model is not None and (not isinstance(model, str) or not is_selectable(model)):
            return jsonify(status="error", message="Nieznany model."), 400
        custom_prompt = body.get('prompt')
        if custom_prompt is not None and (not isinstance(custom_prompt, str) or not custom_prompt.strip()):
            return jsonify(status="error", message="Nieprawidłowy prompt."), 400
        if custom_prompt is not None and len(custom_prompt) > MAX_CUSTOM_PROMPT_CHARS:
            return jsonify(status="error",
                           message=f"Prompt jest za długi (maks. {MAX_CUSTOM_PROMPT_CHARS} znaków)."), 400
        chapter = best_chapter(text, forms)
        if chapter is None:
            return jsonify(status="error", message="Nie znaleziono w tekście rozdziału z tą organizacją."), 404
        prompt = custom_prompt if custom_prompt is not None else build_organization_prompt(
            entity.entity_text, chapter[0], chapter[1], doc_title)
        result = run_organization_description(prompt, model)
        return jsonify(status="success", result_status=result["status"], description=result["description"],
                       model=result["model"], latency_ms=result["latency_ms"],
                       error_code=result.get("error_code"), chapter_title=chapter[0]), 200
    sentences = context_sentences(text, forms)
    if not sentences:
        return jsonify(status="error", message="Nie znaleziono w tekście zdań z tym wydarzeniem."), 404
    description = describe_event(entity.entity_text, sentences, doc_title)
    return jsonify(status="success", description=description, sentences=sentences), 200


@app.route('/website_entities/<int:entity_id>/describe/preview', methods=['POST'])
def website_entities_describe_preview(entity_id: int):
    """The prompt ``/describe`` would send for an organization plus the selectable models (no LLM call)."""
    from library.article_tagging import _tagging_model
    from library.db.models import DocumentEntity
    from library.event_description import MAX_CHAPTER_CHARS, best_chapter, build_organization_prompt
    from library.llm_model_registry import selectable_models

    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type != "orgName":
        return jsonify(status="error", message="Podgląd dotyczy tylko organizacji."), 400
    document = session.get(Document, entity.document_id)
    text = (document.text_md or document.text or "") if document is not None else ""
    chapter = best_chapter(text, [entity.entity_text, *(entity.variants or [])])
    if chapter is None:
        return jsonify(status="error", message="Nie znaleziono w tekście rozdziału z tą organizacją."), 404
    prompt = build_organization_prompt(entity.entity_text, chapter[0], chapter[1],
                                       getattr(document, "title", "") or "")
    return jsonify(status="success", prompt=prompt, chapter_title=chapter[0],
                   truncated=len(chapter[1]) > MAX_CHAPTER_CHARS, default_model=_tagging_model(),
                   models=selectable_models()), 200


@app.route('/website_entities/<int:entity_id>/describe/arena', methods=['POST'])
def website_entities_describe_arena(entity_id: int):
    """Run one prompt through 2-4 allowlisted models in parallel and return every proposal (nothing stored).

    Body: ``{"models": [...], "prompt"?}``. The prompt is built once (or taken verbatim from the body) and
    sent identically to every model; one model failing or timing out never hides the others.
    """
    from concurrent.futures import ThreadPoolExecutor, wait

    from library.db.models import DocumentEntity
    from library.event_description import (
        MAX_CUSTOM_PROMPT_CHARS, best_chapter, build_organization_prompt, run_organization_description,
    )
    from library.llm_model_registry import selectable_models

    ARENA_DEADLINE_SECONDS = 90

    body = request.get_json(silent=True) or {}
    models = body.get('models')
    if not isinstance(models, list) or not all(isinstance(item, str) for item in models):
        return jsonify(status="error", message="Podaj listę modeli."), 400
    if not 2 <= len(models) <= 4 or len(set(models)) != len(models):
        return jsonify(status="error", message="Wybierz od 2 do 4 różnych modeli."), 400
    labels = {item["id"]: item["label"] for item in selectable_models()}
    if any(model not in labels for model in models):
        return jsonify(status="error", message="Nieznany model."), 400
    custom_prompt = body.get('prompt')
    if custom_prompt is not None and (not isinstance(custom_prompt, str) or not custom_prompt.strip()
                                      or len(custom_prompt) > MAX_CUSTOM_PROMPT_CHARS):
        return jsonify(status="error", message="Nieprawidłowy prompt."), 400

    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type != "orgName":
        return jsonify(status="error", message="Arena dotyczy tylko organizacji."), 400
    document = session.get(Document, entity.document_id)
    text = (document.text_md or document.text or "") if document is not None else ""
    chapter = best_chapter(text, [entity.entity_text, *(entity.variants or [])])
    if chapter is None:
        return jsonify(status="error", message="Nie znaleziono w tekście rozdziału z tą organizacją."), 404
    prompt = custom_prompt if custom_prompt is not None else build_organization_prompt(
        entity.entity_text, chapter[0], chapter[1], getattr(document, "title", "") or "")

    # The DB session is not shared with the workers: they only call the model with the finished prompt.
    pool = ThreadPoolExecutor(max_workers=len(models))
    futures = {model: pool.submit(run_organization_description, prompt, model) for model in models}
    wait(futures.values(), timeout=ARENA_DEADLINE_SECONDS)
    results = []
    for model, future in futures.items():
        if future.done():
            result = future.result()
        else:
            result = {"status": "error", "description": None, "model": model, "error_code": "Timeout",
                      "latency_ms": ARENA_DEADLINE_SECONDS * 1000, "tokens": None, "cost": None, "currency": None}
        results.append({
            "model": model, "label": labels[model], "result_status": result["status"],
            "description": result["description"], "latency_ms": result["latency_ms"],
            "tokens": result.get("tokens"), "cost": result.get("cost"), "currency": result.get("currency"),
            "error_code": result.get("error_code"),
        })
    pool.shutdown(wait=False, cancel_futures=True)
    return jsonify(status="success", results=results, chapter_title=chapter[0]), 200


@app.route('/website_entities/<int:entity_id>/description', methods=['PUT'])
def website_entities_set_description(entity_id: int):
    """Store (or clear, with an empty string) the reviewer-approved description of an event entity."""
    from library.db.models import DocumentEntity

    data = request.get_json(silent=True) or {}
    description = data.get('description')
    if not isinstance(description, str) or len(description) > 2000:
        return jsonify(status="error", message="Nieprawidłowy opis."), 400
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type != "eventName":
        return jsonify(status="error", message="Opis dotyczy tylko wydarzeń."), 400
    from library.entity_review_audit import record_entity_decision

    try:
        entity.description = description.strip() or None
        # Audited so the text survives a reopen for editing (replay_manual_added_entities).
        record_entity_decision(
            session, document_id=entity.document_id, document_entity_id=entity.id, entity_type="eventName",
            entity_text=entity.entity_text, decision="entity_described", details={"description": entity.description},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Saving the description of entity %s failed", entity_id)
        return jsonify(status="error", message="Nie udało się zapisać opisu."), 500
    return jsonify(status="success", entity_id=entity.id, description=entity.description), 200


def _named_entity_index(entity_type: str):
    """Rows of one manual entity type grouped by case-folded name across documents (events, products).

    Query: ``q`` (name or description contains, case-insensitive), ``limit`` (default 50, max 200),
    ``offset``. Returns ``(groups_page, total, limit, offset)`` or a 400 response. Each group: name, description (first
    non-empty one), mentions, document_count and documents (id, title, mentions, entity_id).
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import DocumentEntity

    try:
        limit = min(max(int(request.args.get('limit', 50)), 1), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        return jsonify(status="error", message="limit i offset muszą być liczbami."), 400
    needle = (request.args.get('q') or "").strip().lower()
    session = get_scoped_session()
    query = sa_select(DocumentEntity, Document.title).join(Document, Document.id == DocumentEntity.document_id).where(
        DocumentEntity.entity_type == entity_type)
    if needle:
        like = f"%{needle}%"
        query = query.where(sa_func.lower(DocumentEntity.entity_text).like(like)
                            | sa_func.lower(sa_func.coalesce(DocumentEntity.description, "")).like(like))
    groups: dict[str, dict] = {}
    for entity, title in session.execute(query.order_by(DocumentEntity.entity_text, DocumentEntity.document_id)).all():
        group = groups.setdefault(entity.entity_text.casefold(), {
            "name": entity.entity_text, "description": None, "mentions": 0, "documents": [],
        })
        group["mentions"] += entity.mention_count or 0
        group["description"] = group["description"] or entity.description
        group["documents"].append({"id": entity.document_id, "title": title, "mentions": entity.mention_count,
                                   "entity_id": entity.id})
    rows = sorted(groups.values(), key=lambda group: group["name"].casefold())
    page = [{**group, "document_count": len(group["documents"])} for group in rows[offset:offset + limit]]
    return page, len(rows), limit, offset


@app.route('/entity_events', methods=['GET'])
def entity_events_list():
    """Index of the events added to documents, grouped by case-folded name (``/world-events`` page)."""
    result = _named_entity_index("eventName")
    if not isinstance(result, tuple):
        return result
    page, total, limit, offset = result
    return jsonify(status="success", total=total, limit=limit, offset=offset, events=page), 200


@app.route('/entity_products', methods=['GET'])
def entity_products_list():
    """Index of the products/systems added to documents, grouped by case-folded name (``/products`` page).

    Same query and row shape as ``/entity_events``, under ``products``.
    """
    result = _named_entity_index("productName")
    if not isinstance(result, tuple):
        return result
    page, total, limit, offset = result
    return jsonify(status="success", total=total, limit=limit, offset=offset, products=page), 200


@app.route('/entity_product', methods=['GET'])
def entity_product_detail():
    """One product page (``/products/:name``): description, spellings and every document mentioning it.

    Query: ``name`` (case-insensitive). Answers name, description, ``variants`` (surface forms found in
    the documents), mentions and ``documents`` (id, title, mentions, entity_id, document_type, ingested_at),
    most mentions first; 404 when no document has such a product.
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import DocumentEntity

    name = (request.args.get('name') or "").strip()
    if not name:
        return jsonify(status="error", message="Brakuje parametru name."), 400
    session = get_scoped_session()
    rows = session.execute(
        sa_select(DocumentEntity, Document.title, Document.document_type, Document.ingested_at)
        .join(Document, Document.id == DocumentEntity.document_id)
        .where(DocumentEntity.entity_type == "productName", sa_func.lower(DocumentEntity.entity_text) == name.lower())
        .order_by(DocumentEntity.mention_count.desc(), DocumentEntity.document_id)
    ).all()
    if not rows:
        return jsonify(status="error", message="Nie znaleziono produktu."), 404
    variants: list[str] = []
    for entity, _title, _type, _ingested in rows:
        for form in entity.variants or []:
            if form.casefold() != name.casefold() and form not in variants:
                variants.append(form)
    return jsonify(
        status="success", name=rows[0][0].entity_text,
        description=next((entity.description for entity, *_rest in rows if entity.description), None),
        variants=variants, mentions=sum(entity.mention_count or 0 for entity, *_rest in rows),
        documents=[{"id": entity.document_id, "title": title, "mentions": entity.mention_count, "entity_id": entity.id,
                    "document_type": str(document_type) if document_type else None,
                    "ingested_at": ingested_at.isoformat() if ingested_at else None}
                   for entity, title, document_type, ingested_at in rows],
    ), 200


@app.route('/entity_product/description', methods=['PUT'])
def entity_product_set_description():
    """Store (or clear, with an empty string) the description of a product, shared by all its documents.

    Body: ``{"name", "description"}``. Every ``productName`` row of that name gets the text and each is
    audited as ``entity_described``, so it survives a reopen for editing (``replay_manual_added_entities``).
    """
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import DocumentEntity
    from library.entity_review_audit import record_entity_decision

    data = request.get_json(silent=True) or {}
    name, description = data.get('name'), data.get('description')
    if not isinstance(name, str) or not name.strip() or not isinstance(description, str) or len(description) > 2000:
        return jsonify(status="error", message="Nieprawidłowa nazwa lub opis."), 400
    session = get_scoped_session()
    entities = session.scalars(sa_select(DocumentEntity).where(
        DocumentEntity.entity_type == "productName", sa_func.lower(DocumentEntity.entity_text) == name.strip().lower(),
    )).all()
    if not entities:
        return jsonify(status="error", message="Nie znaleziono produktu."), 404
    try:
        for entity in entities:
            entity.description = description.strip() or None
            record_entity_decision(
                session, document_id=entity.document_id, document_entity_id=entity.id, entity_type="productName",
                entity_text=entity.entity_text, decision="entity_described", details={"description": entity.description},
            )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Saving the description of product %r failed", name)
        return jsonify(status="error", message="Nie udało się zapisać opisu."), 500
    return jsonify(status="success", name=entities[0].entity_text, description=entities[0].description,
                   documents=len(entities)), 200


@app.route('/document/<int:document_id>/entities/add_mention', methods=['POST'])
def document_entities_add_mention(document_id: int):
    """Add an entity from a fragment of the text a reviewer selected (context menu on /ner/:id).

    Body: {"text": "kaliningradzkiej enklawy",
    "entity_type": "persName"|"orgName"|"placeName"|"eventName"|"productName", "name": "Obwód Kaliningradzki"?}. ``text`` must occur in the document; ``name`` is the canonical
    name (default: the text) — an existing same-named entity gets the mentions and the surface form added.
    A fragment that already is an entity (or one of its surface forms) answers 409 with that entity: use
    its own menu to retype it. A place is geocoded once (a country gets its ``kraj-*`` tag), an organization
    is resolved through the registry, a person through the person registry. Audited as ``entity_added`` and
    re-created after a reopen for editing (library/entity_overrides.py).
    """
    from sqlalchemy import select as sa_select
    from library import person_registry
    from library.country_gazetteer import country_tag_for
    from library.db.models import DocumentEntity
    from library.entity_overrides import ADDABLE_ENTITY_TYPES, add_manual_entity, count_mentions
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import geocode_single_place

    data = request.get_json(silent=True) or {}
    surface, name = data.get('text'), data.get('name')
    entity_type = data.get('entity_type')
    if not isinstance(surface, str) or not surface.strip() or len(surface) > 200:
        return jsonify(status="error", message="Nieprawidłowy zaznaczony tekst."), 400
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 200):
        return jsonify(status="error", message="Nieprawidłowa nazwa."), 400
    if entity_type not in ADDABLE_ENTITY_TYPES:
        return jsonify(
            status="error", message="entity_type musi być persName, orgName, placeName, eventName lub productName."), 400
    surface = " ".join(surface.split())
    name = " ".join(name.split()) if name else None
    session = get_scoped_session()
    document = session.get(Document, document_id)
    if document is None:
        return jsonify(status="error", message="Nie znaleziono dokumentu."), 404
    text = document.text_md or document.text or ""
    count = count_mentions(text, surface)
    if count == 0:
        return jsonify(status="error", message="Zaznaczonego fragmentu nie ma w tekście dokumentu."), 400
    keys = {surface.casefold()}
    for existing in session.scalars(sa_select(DocumentEntity).where(DocumentEntity.document_id == document_id)).all():
        if keys & {existing.entity_text.casefold(), *(v.casefold() for v in (existing.variants or []))}:
            return jsonify(status="error", code="entity_exists", message="Ten fragment jest już encją.",
                           entity={"id": existing.id, "entity_type": existing.entity_type,
                                   "entity_text": existing.entity_text}), 409
    try:
        row, organization = add_manual_entity(session, document_id, entity_type, surface, name, count)
        if entity_type == "placeName":
            tag = country_tag_for(row.entity_text)
            if tag is not None:
                existing_tags = [t.strip() for t in (document.tags or "").split(",") if t.strip()]
                if tag not in existing_tags:
                    document.tags = ",".join([*existing_tags, tag])
            elif row.geocode_id is None:
                geocode_single_place(session, document, row)
        record_entity_decision(
            session, document_id=document_id, document_entity_id=row.id, entity_type=entity_type,
            entity_text=row.entity_text, decision="entity_added",
            details={"surface": surface, "name": row.entity_text, "count": count},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Adding %s %r to document %s failed", entity_type, surface, document_id)
        return jsonify(status="error", message="Nie udało się dodać encji."), 500
    linked = []
    if entity_type == "persName":
        try:
            resolved = person_registry.resolve_document_persons(session, document, text, only_names=[row.entity_text])
            session.commit()
            linked = [canonical for _name, canonical, _conf in (resolved or {}).get("linked", [])]
        except Exception:
            session.rollback()
            logging.exception("Person resolution after adding %r to document %s failed", row.entity_text, document_id)
    return jsonify(status="success", entity_id=row.id, entity_type=row.entity_type, entity_text=row.entity_text,
                   mention_count=row.mention_count, organization_id=getattr(organization, "id", None),
                   linked=linked), 201


@app.route('/website_entities/<int:entity_id>/split_place', methods=['POST'])
def website_entities_split_place(entity_id: int):
    """Split a place entity that lists several places (NER: "Pakistanem Afganistanem") into one per part.

    Body: {"parts": ["Pakistan", "Afganistan"]} — 2-6 distinct non-empty names. Country parts add
    their ``kraj-*`` tag; other new parts are geocoded once through the cache. The decision is
    audited as ``place_split`` and replayed after entity refreshes (library/entity_overrides.py).
    """
    from library.country_gazetteer import canonical_country_name, country_tag_for
    from library.db.models import DocumentEntity
    from library.entity_overrides import split_place_entity
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES, geocode_single_place, remove_orphaned_tag

    data = request.get_json(silent=True) or {}
    raw_parts = data.get('parts')
    if not isinstance(raw_parts, list) or not all(isinstance(p, str) for p in raw_parts):
        return jsonify(status="error", message="Pole parts musi być listą nazw."), 400
    parts = [p.strip() for p in raw_parts]
    if not 2 <= len(parts) <= 6 or any(not p or len(p) > 200 for p in parts) \
            or len({p.casefold() for p in parts}) != len(parts):
        return jsonify(status="error", message="Podaj od 2 do 6 różnych, niepustych nazw."), 400

    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type not in PLACE_ENTITY_TYPES:
        return jsonify(status="error", message="Encja nie jest miejscem."), 400
    try:
        document = session.get(Document, entity.document_id)
        old_text, old_type, old_variants = entity.entity_text, entity.entity_type, list(entity.variants or [])
        removed_tag = remove_orphaned_tag(session, document, entity) if document is not None else None
        rows = split_place_entity(session, entity, parts)
        countries = []
        for row in rows:
            tag = country_tag_for(row.entity_text)
            if tag is not None:
                countries.append(canonical_country_name(row.entity_text))
                existing = [t.strip() for t in ((document.tags if document else "") or "").split(",") if t.strip()]
                if document is not None and tag not in existing:
                    document.tags = ",".join([*existing, tag])
            elif row.geocode_id is None and document is not None:
                geocode_single_place(session, document, row)
        record_entity_decision(
            session, document_id=document.id if document else rows[0].document_id, document_entity_id=rows[0].id,
            entity_type=old_type, entity_text=old_text, decision="place_split",
            details={"parts": parts, "variants": old_variants, "removed_tag": removed_tag},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Place split failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się podzielić miejsca."), 500
    return jsonify(status="success", entity_ids=[row.id for row in rows], parts=parts,
                   countries=countries, removed_tag=removed_tag), 200


@app.route('/website_entities/<int:entity_id>/split_organization', methods=['POST'])
def website_entities_split_organization(entity_id: int):
    """Split an orgName entity made of glued mentions (NER: "NATO Moskwa") into one per part.

    Body: {"parts": ["NATO", "Moskwa"]} — 2-6 distinct non-empty names. Each part is resolved through
    the organization registry and gets its own ``source='manual'`` row and document link; the glued row
    and its link are dropped (the organization it pointed at stays in the registry). The decision is
    audited as ``organization_split`` and replayed after entity refreshes (library/entity_overrides.py).
    """
    from library.db.models import DocumentEntity
    from library.entity_overrides import split_organization_entity
    from library.entity_review_audit import record_entity_decision

    data = request.get_json(silent=True) or {}
    raw_parts = data.get('parts')
    if not isinstance(raw_parts, list) or not all(isinstance(p, str) for p in raw_parts):
        return jsonify(status="error", message="Pole parts musi być listą nazw."), 400
    parts = [p.strip() for p in raw_parts]
    if not 2 <= len(parts) <= 6 or any(not p or len(p) > 200 for p in parts) \
            or len({p.casefold() for p in parts}) != len(parts):
        return jsonify(status="error", message="Podaj od 2 do 6 różnych, niepustych nazw."), 400

    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return jsonify(status="error", message="Nie znaleziono encji."), 404
    if entity.entity_type != "orgName":
        return jsonify(status="error", message="Encja nie jest organizacją."), 400
    try:
        old_text, old_variants, document_id = entity.entity_text, list(entity.variants or []), entity.document_id
        results = split_organization_entity(session, entity, parts)
        rows = [row for row, _organization in results]
        record_entity_decision(
            session, document_id=document_id, document_entity_id=rows[0].id,
            entity_type="orgName", entity_text=old_text, decision="organization_split",
            details={
                "parts": parts, "variants": old_variants,
                "part_names": [row.entity_text for row in rows],
                "organization_ids": [organization.id for _row, organization in results],
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("Organization split failed for entity %s", entity_id)
        return jsonify(status="error", message="Nie udało się podzielić organizacji."), 500
    return jsonify(status="success", entity_ids=[row.id for row in rows], parts=parts,
                   organization_ids=[organization.id for _row, organization in results]), 200


@app.route('/website_entities/<int:entity_id>', methods=['DELETE', 'OPTIONS'])
def website_entities_delete(entity_id: int):
    """Delete a stored NER entity row (editor UI).

    For persName entities the matching document_persons link (same document,
    raw_mention == entity_text) is removed too; a person left with no links
    is dropped from the registry. For geogName/placeName entities, the
    corresponding miejsce-* tag (library/place_verification.py) is dropped
    from the document too, unless another entity of this document still maps
    to the same canonical place."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.db.models import DocumentEntity, DocumentOrganization, DocumentPerson
    from library.entity_review_audit import record_entity_decision
    from library.place_verification import PLACE_ENTITY_TYPES, remove_orphaned_tag
    from library.relationship_audit import audit_removals

    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "deleted")
    allowed_decisions = {"deleted", "rejected", "excluded_global", "excluded_author", "excluded_document"}
    allowed_reasons = {
        "not_a_person", "misread_name", "fictional_or_collective", "organization_as_person",
        "duplicate_person", "wrong_person", "irrelevant", "other",
    }
    if decision not in allowed_decisions:
        return {"status": "error", "message": "invalid entity review decision"}, 400
    reason_code = (data.get("reason_code") or "").strip() or None
    comment = (data.get("comment") or "").strip() or None
    if reason_code is not None and reason_code not in allowed_reasons:
        return {"status": "error", "message": "invalid entity review reason"}, 400
    if reason_code == "other" and not comment:
        return {"status": "error", "message": "comment is required for other reason"}, 400
    session = get_scoped_session()
    entity = session.get(DocumentEntity, entity_id)
    if entity is None:
        return {"status": "error", "message": "Entity not found"}, 404

    link_result = None
    try:
        if entity.entity_type == "persName":
            link = session.execute(
                sa_select(DocumentPerson).where(
                    DocumentPerson.document_id == entity.document_id,
                    sa_func.lower(DocumentPerson.raw_mention) == entity.entity_text.lower(),
                )
            ).scalars().first()
            if link is not None:
                link_result = person_registry.reject_review_link(session, link)
        record_entity_decision(
            session,
            document_id=entity.document_id,
            document_entity_id=entity.id,
            document_person_id=getattr(link, "id", None) if entity.entity_type == "persName" else None,
            person_id=getattr(link, "person_id", None) if entity.entity_type == "persName" else None,
            entity_type=entity.entity_type,
            entity_text=entity.entity_text,
            decision=decision,
            reason_code=reason_code,
            comment=comment,
            original_confidence=(
                getattr(link, "confidence", None) if entity.entity_type == "persName" else None
            ),
            source_excerpt=(
                getattr(link, "source_excerpt", None) if entity.entity_type == "persName" else None
            ),
            details={
                "mention_count": entity.mention_count,
                "variants": list(entity.variants or []),
            },
        )
        removed_tag = None
        organization_link_removed = False
        if entity.entity_type == "orgName":
            organization_link = session.scalar(sa_select(DocumentOrganization).where(
                DocumentOrganization.document_id == entity.document_id,
                DocumentOrganization.document_entity_id == entity.id,
            ))
            # An editor deletion must not leave a derived organization link in
            # the graph. Explicitly approved links remain protected: they are
            # a deliberate reader decision rather than NER-derived data.
            if organization_link is not None and organization_link.review_status != "approved":
                audit_removals(session, entity.document_id, "organization", "entity_editor_delete",
                               [organization_link], lambda row: {
                                   "organization_id": row.organization_id,
                                   "document_entity_id": row.document_entity_id,
                                   "confidence": row.confidence,
                                   "review_status": row.review_status,
                               })
                session.delete(organization_link)
                organization_link_removed = True
        if entity.entity_type in PLACE_ENTITY_TYPES:
            document = session.get(Document, entity.document_id)
            if document is not None:
                removed_tag = remove_orphaned_tag(session, document, entity)
        session.delete(entity)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("entity delete failed for entity %s", entity_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "deleted_entity_id": entity_id,
                    "removed_tag": removed_tag,
                    "organization_link_removed": organization_link_removed,
                    "person_link_removed": link_result is not None,
                    "person_deleted": bool(link_result and link_result.get("person_deleted"))}), 200


@app.route('/organizations', methods=['GET', 'POST', 'OPTIONS'])
def organizations_collection():
    """GET: search the global organization registry by name/alias.
    POST: manually create an organization. Body: {"canonical_name": "...", "organization_type": "..."}.
    See docs/organization-ner-alias-plan.md."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from sqlalchemy import func, or_, select
    from library.db.models import DocumentOrganization, Organization, OrganizationAlias

    session = get_scoped_session()

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        canonical_name = (data.get('canonical_name') or "").strip()
        if not canonical_name:
            return {"status": "error", "message": "canonical_name is required"}, 400
        organization = Organization(
            canonical_name=canonical_name,
            organization_type=(data.get('organization_type') or "").strip() or None,
            description=(data.get('description') or "").strip() or None,
        )
        session.add(organization)
        try:
            session.commit()
        except Exception:
            session.rollback()
            logging.exception("organization create failed")
            return {"status": "error", "message": "DB error"}, 500
        return jsonify({"status": "success", "id": organization.id,
                        "canonical_name": organization.canonical_name}), 201

    query = (request.args.get('q') or '').strip()
    statement = (
        select(
            Organization,
            func.count(func.distinct(DocumentOrganization.document_id)).label('document_count'),
        )
        .outerjoin(DocumentOrganization, DocumentOrganization.organization_id == Organization.id)
        .group_by(Organization.id)
        .order_by(
            func.count(func.distinct(DocumentOrganization.document_id)).desc(),
            Organization.canonical_name,
        )
    )
    if query:
        pattern = f"%{query}%"
        alias_match = select(OrganizationAlias.organization_id).where(OrganizationAlias.alias.ilike(pattern))
        statement = statement.where(or_(
            Organization.canonical_name.ilike(pattern),
            Organization.id.in_(alias_match),
        ))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    offset = max(request.args.get('offset', 0, type=int), 0)
    limit = min(max(request.args.get('limit', 50, type=int), 1), 100)
    rows = session.execute(statement.offset(offset).limit(limit)).all()
    entries = [{
        "id": organization.id,
        "canonical_name": organization.canonical_name,
        "organization_type": organization.organization_type,
        "description": organization.description,
        "aliases": [alias.alias for alias in organization.aliases],
        "document_count": count,
    } for organization, count in rows]
    return {"status": "success", "count": total, "total": total, "limit": limit, "offset": offset, "entries": entries}, 200


@app.route('/organizations/<int:organization_id>', methods=['GET'])
def organization_get(organization_id: int):
    """A single organization with its aliases, document count, and any
    registered name collisions (organization_ambiguous_aliases) — surfaced
    as ambiguous_with so the /organizations/:id panel can warn that a text
    resolving here (e.g. "Africa Corps") is also a candidate for another,
    unrelated organization (e.g. WWII's "Afrika Korps"), resolved per-mention
    by entity_service's context-LLM step rather than always landing here."""
    from sqlalchemy import func, select
    from library import organization_location
    from library.db.models import DocumentOrganization, Organization, OrganizationAmbiguousAlias

    session = get_scoped_session()
    organization = session.get(Organization, organization_id)
    if organization is None:
        return {"status": "error", "message": "Organization not found"}, 404
    document_count = session.scalar(
        select(func.count(func.distinct(DocumentOrganization.document_id)))
        .where(DocumentOrganization.organization_id == organization_id)
    )
    own_ambiguous_aliases = session.execute(
        select(OrganizationAmbiguousAlias).where(
            OrganizationAmbiguousAlias.organization_id == organization_id,
            OrganizationAmbiguousAlias.status == "approved",
        )
    ).scalars().all()
    ambiguous_with = []
    for row in own_ambiguous_aliases:
        other_rows = session.execute(
            select(OrganizationAmbiguousAlias, Organization)
            .join(Organization, Organization.id == OrganizationAmbiguousAlias.organization_id)
            .where(
                OrganizationAmbiguousAlias.normalized_alias == row.normalized_alias,
                OrganizationAmbiguousAlias.organization_id != organization_id,
                OrganizationAmbiguousAlias.status == "approved",
            )
        ).all()
        if other_rows:
            ambiguous_with.append({
                "alias": row.alias,
                "context_hint": row.context_hint,
                "other_organizations": [
                    {
                        "id": other_org.id,
                        "canonical_name": other_org.canonical_name,
                        "organization_type": other_org.organization_type,
                        "description": other_org.description,
                        "context_hint": other_alias.context_hint,
                    }
                    for other_alias, other_org in other_rows
                ],
            })
    return {
        "status": "success",
        "id": organization.id,
        "canonical_name": organization.canonical_name,
        "organization_type": organization.organization_type,
        "description": organization.description,
        **_organization_location_fields(organization),
        "aliases": [
            {"id": a.id, "alias": a.alias, "alias_kind": a.alias_kind, "created_by": a.created_by}
            for a in organization.aliases
        ],
        "document_count": document_count or 0,
        "ambiguous_with": ambiguous_with,
        "note": organization_location.organization_note_for(session, organization),
    }, 200


def _organization_location_fields(organization) -> dict:
    """Headquarters / website / Obsidian-note fields shared by the GET and PATCH responses."""
    return {
        "headquarters_address": organization.headquarters_address,
        "latitude": float(organization.latitude) if organization.latitude is not None else None,
        "longitude": float(organization.longitude) if organization.longitude is not None else None,
        "website": organization.website,
        "obsidian_note_path": organization.obsidian_note_path,
        "primary_note_document_id": organization.primary_note_document_id,
    }


@app.route('/organizations/<int:organization_id>/countries', methods=['GET', 'POST', 'OPTIONS'])
def organization_countries(organization_id: int):
    """Countries an organization is based in / operates in / linked to.

    GET: {countries, suggestions, relations} — suggestions are the kraj-* tags of
    the organization's documents (candidates only, never auto-assigned).
    POST: {"country_slug": "jemen", "relation": "operates_in", "note": "..."}
    (relation: based_in | operates_in | linked_to); 201 when created, 200 when
    the pair already existed."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library import organization_location
    from library.db.models import Organization

    session = get_scoped_session()
    if session.get(Organization, organization_id) is None:
        return {"status": "error", "message": "Organization not found"}, 404

    if request.method == 'GET':
        return {
            "status": "success",
            "countries": organization_location.list_countries(session, organization_id),
            "suggestions": organization_location.country_suggestions(session, organization_id),
            "relations": organization_location.COUNTRY_RELATIONS,
        }, 200

    data = request.get_json(silent=True) or {}
    try:
        country, created = organization_location.add_country(
            session, organization_id, data.get('country_slug'), data.get('relation'), data.get('note'))
        session.commit()
    except ValueError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}, 400
    except Exception:
        session.rollback()
        logging.exception("organization country add failed for %s", organization_id)
        return {"status": "error", "message": "DB error"}, 500
    return {"status": "success", "country": country}, 201 if created else 200


@app.route('/organizations/<int:organization_id>/countries/<int:row_id>', methods=['DELETE', 'OPTIONS'])
def organization_country_delete(organization_id: int, row_id: int):
    """Remove one country tie of an organization."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library import organization_location

    session = get_scoped_session()
    try:
        removed = organization_location.remove_country(session, organization_id, row_id)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("organization country delete failed for %s/%s", organization_id, row_id)
        return {"status": "error", "message": "DB error"}, 500
    if not removed:
        return {"status": "error", "message": "Country tie not found"}, 404
    return {"status": "success"}, 200


@app.route('/organizations/<int:organization_id>/related', methods=['GET'])
def organization_related(organization_id: int):
    """Persons and geocoded places that co-occur with an organization in documents —
    the data behind the map and the "powiązane osoby" panel on /organizations/:id."""
    from library import organization_location
    from library.db.models import Organization

    session = get_scoped_session()
    if session.get(Organization, organization_id) is None:
        return {"status": "error", "message": "Organization not found"}, 404
    return {
        "status": "success",
        "persons": organization_location.related_persons(session, organization_id),
        "places": organization_location.related_places(session, organization_id),
    }, 200


@app.route('/organizations/<int:organization_id>/documents', methods=['GET'])
def organization_documents(organization_id: int):
    """All documents mentioning an organization — the organization registry's
    equivalent of GET /person_documents. mention_count/raw_mention come from
    the linked document_entities row (DocumentOrganization.document_entity_id
    is a direct FK, unlike DocumentPerson which stores raw_mention text and
    needs a separate lookup). link_id is the document_organizations row id,
    needed by POST /document/<id>/organizations/<link_id>/approve."""
    from sqlalchemy import select
    from library.db.models import DocumentEntity, DocumentOrganization, Organization

    session = get_scoped_session()
    organization = session.get(Organization, organization_id)
    if organization is None:
        return {"status": "error", "message": "Organization not found"}, 404

    rows = session.execute(
        select(DocumentOrganization, DocumentEntity)
        .outerjoin(DocumentEntity, DocumentEntity.id == DocumentOrganization.document_entity_id)
        .where(DocumentOrganization.organization_id == organization_id)
    ).all()
    documents = [{
        "link_id": link.id,
        "id": link.document.id,
        "title": link.document.title,
        "document_type": link.document.document_type,
        "byline": link.document.byline,
        "raw_mention": entity.entity_text if entity is not None else None,
        "mention_count": entity.mention_count if entity is not None else 0,
        "confidence": link.confidence,
        "review_status": link.review_status,
    } for link, entity in rows]
    documents.sort(key=lambda d: -d["mention_count"])
    return {
        "status": "success",
        "organization": {"id": organization.id, "canonical_name": organization.canonical_name,
                         "description": organization.description,
                         "organization_type": organization.organization_type},
        "documents": documents,
    }, 200


@app.route('/organizations/<int:organization_id>', methods=['DELETE', 'OPTIONS'])
def organization_delete(organization_id: int):
    """Delete an organization nothing depends on (an orphan left by a split or a rename).

    409 with the reason when documents still link to it, an information source is bound to it, or it is a
    country organization. On success its aliases, country ties and ambiguous aliases go with it; the
    response reports how many of each (``removed``)."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library import organization_registry
    from library.db.models import Organization

    session = get_scoped_session()
    organization = session.get(Organization, organization_id)
    if organization is None:
        return {"status": "error", "message": "Organization not found"}, 404
    name = organization.canonical_name
    try:
        removed = organization_registry.delete_unused_organization(session, organization)
        session.commit()
    except organization_registry.OrganizationInUseError as exc:
        session.rollback()
        return jsonify(status="error", message=exc.reason, **exc.counts), 409
    except Exception:
        session.rollback()
        logging.exception("Organization delete failed for %s", organization_id)
        return {"status": "error", "message": "Nie udało się usunąć organizacji."}, 500
    return jsonify(status="success", deleted_organization_id=organization_id, canonical_name=name, removed=removed), 200


@app.route('/organizations/<int:organization_id>', methods=['PATCH', 'OPTIONS'])
def organization_update(organization_id: int):
    """Edit an organization's canonical_name/description/type — shown as a
    tooltip on its chip in the reader (EntitiesPanel). Body:
    {"canonical_name": "..."} and/or {"description": "..."} and/or
    {"organization_type": "..."}. Empty string clears description/type;
    canonical_name must not be blanked. Renaming keeps the old name
    resolvable as an alias (organization_registry.rename()) — needed after
    organization_registry.merge() leaves a raw pre-Faza-1/5 NER lemma dump
    (e.g. "unia europejski") as the surviving canonical_name."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from sqlalchemy import select as sa_select

    from library import organization_registry
    from library.db.models import InformationSource, Organization
    from library.organization_source_sync import SourceConflictError, rename_organization, set_description

    session = get_scoped_session()
    organization = session.get(Organization, organization_id)
    if organization is None:
        return {"status": "error", "message": "Organization not found"}, 404

    data = request.get_json(silent=True) or {}
    rename_result = None
    if 'canonical_name' in data:
        new_name = (data.get('canonical_name') or "").strip()
        if not new_name:
            return {"status": "error", "message": "canonical_name must not be empty"}, 400
        try:
            # Also renames the document entities and the information source bound
            # to this organization (merging a same-named duplicate source).
            rename_result = rename_organization(session, organization, new_name)
        except organization_registry.AliasConflictError as exc:
            session.rollback()
            return {"status": "error", "message": str(exc),
                    "existing_organization_id": exc.existing_organization_id}, 409
        except SourceConflictError as exc:
            session.rollback()
            return {"status": "error", "message": str(exc),
                    "existing_organization_id": exc.existing_organization_id}, 409
        except ValueError as exc:
            session.rollback()
            return {"status": "error", "message": str(exc)}, 400
        except Exception as exc:
            session.rollback()
            logging.exception("organization rename failed: id=%s %r -> %r", organization_id,
                              organization.canonical_name, new_name)
            return {"status": "error",
                    "message": f"Błąd serwera przy zmianie nazwy: {type(exc).__name__}: {str(exc)[:300]}"}, 500
    if 'description' in data:
        # One description for the organization and the information source bound to it.
        linked_source = session.scalar(sa_select(InformationSource).where(
            InformationSource.organization_id == organization.id))
        set_description(organization, linked_source, (data.get('description') or "").strip() or None)
    if 'organization_type' in data:
        organization.organization_type = (data.get('organization_type') or "").strip() or None
    for field in ('website', 'obsidian_note_path'):
        if field in data:
            setattr(organization, field, (data.get(field) or "").strip() or None)
    if 'primary_note_document_id' in data:
        from library.db.models import Document
        raw_note_id = data.get('primary_note_document_id')
        if raw_note_id in (None, ""):
            organization.primary_note_document_id = None
        else:
            try:
                note_id = int(raw_note_id)
            except (TypeError, ValueError):
                session.rollback()
                return {"status": "error", "message": "primary_note_document_id must be an integer"}, 400
            note_document = session.get(Document, note_id)
            if note_document is None or note_document.document_type != "obsidian_note":
                session.rollback()
                return {"status": "error",
                        "message": "primary_note_document_id must point at an obsidian_note document"}, 400
            organization.primary_note_document_id = note_id
    elif 'obsidian_note_path' in data and organization.primary_note_document_id is None:
        # A new vault path that resolves to an imported note links it right away.
        from library import organization_location
        resolved_note = organization_location.organization_note(session, organization.obsidian_note_path)
        if resolved_note is not None:
            organization.primary_note_document_id = resolved_note["document_id"]

    geocoded = None
    if 'headquarters_address' in data:
        from library import organization_location
        organization.headquarters_address = (data.get('headquarters_address') or "").strip() or None
        has_manual_point = data.get('latitude') is not None and data.get('longitude') is not None
        if not has_manual_point:
            geocoded = organization_location.geocode_headquarters(session, organization)
    if 'latitude' in data or 'longitude' in data:
        try:
            lat, lon = data.get('latitude'), data.get('longitude')
            if lat in (None, "") and lon in (None, ""):
                organization.latitude = organization.longitude = None
            else:
                lat, lon = float(lat), float(lon)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("coordinates out of range")
                organization.latitude, organization.longitude = lat, lon
        except (TypeError, ValueError):
            session.rollback()
            return {"status": "error", "message": "latitude and longitude must both be valid coordinates"}, 400

    try:
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("organization update failed for %s", organization_id)
        return {"status": "error", "message": "DB error"}, 500

    from library import organization_location
    return jsonify({"status": "success", "id": organization.id,
                    "canonical_name": organization.canonical_name,
                    "description": organization.description,
                    "organization_type": organization.organization_type,
                    **_organization_location_fields(organization),
                    "note": organization_location.organization_note_for(session, organization),
                    "geocoded": geocoded,
                    "rename": rename_result}), 200


@app.route('/information_sources/<int:source_id>', methods=['PATCH', 'OPTIONS'])
def information_source_update(source_id: int):
    """Edit an information source's type, domain and description — the data shown for a
    cited source in the entities panel. Body: any of {"source_type", "domain",
    "description"}; an empty string clears a field. The domain is normalized from a pasted
    URL ("https://www.telegraph.co.uk/" -> "telegraph.co.uk"). The description is shared
    with the organization bound to the source (one text for both)."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import InformationSource
    from library.organization_source_sync import update_source_details

    session = get_scoped_session()
    source = session.get(InformationSource, source_id)
    if source is None:
        return {"status": "error", "message": "Information source not found"}, 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"status": "error", "message": "JSON object body required"}, 400
    try:
        update_source_details(session, source, data)
        session.commit()
    except ValueError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}, 400
    except Exception:
        session.rollback()
        logging.exception("information source update failed for %s", source_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "id": source.id, "canonical_name": source.canonical_name,
                    "source_type": source.source_type, "domain": source.domain,
                    "description": source.description,
                    "organization_id": source.organization_id}), 200


@app.route('/organizations/<int:organization_id>/aliases', methods=['POST', 'OPTIONS'])
def organization_alias_add(organization_id: int):
    """Manually add a global alias to an organization.

    Body: {"alias": "...", "alias_kind": "manual"|"inflection"|"abbreviation"|"former_name"}.
    Idempotent for the same organization; 409 when the alias already belongs
    to a different organization."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library import organization_registry
    from library.db.models import Organization

    data = request.get_json(silent=True) or {}
    alias = (data.get('alias') or "").strip()
    if not alias:
        return {"status": "error", "message": "alias is required"}, 400
    alias_kind = (data.get('alias_kind') or "manual").strip()
    if alias_kind not in {"inflection", "abbreviation", "former_name", "manual", "ner_observed"}:
        return {"status": "error", "message": "invalid alias_kind"}, 400

    session = get_scoped_session()
    organization = session.get(Organization, organization_id)
    if organization is None:
        return {"status": "error", "message": "Organization not found"}, 404

    try:
        row = organization_registry.add_alias(session, organization, alias, alias_kind=alias_kind)
        session.commit()
    except organization_registry.AliasConflictError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc),
                "existing_organization_id": exc.existing_organization_id}, 409
    except Exception:
        session.rollback()
        logging.exception("alias add failed for organization %s", organization_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "organization_id": organization_id,
                    "alias_id": row.id, "alias": row.alias}), 200


@app.route('/organizations/<int:organization_id>/aliases/<int:alias_id>', methods=['DELETE', 'OPTIONS'])
def organization_alias_delete(organization_id: int, alias_id: int):
    """Remove a global alias. Does not touch audit history — future NER runs
    simply stop applying this rule (docs/organization-ner-alias-plan.md)."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import OrganizationAlias

    session = get_scoped_session()
    alias = session.get(OrganizationAlias, alias_id)
    if alias is None or alias.organization_id != organization_id:
        return {"status": "error", "message": "Alias not found"}, 404

    try:
        session.delete(alias)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("alias delete failed for organization %s alias %s", organization_id, alias_id)
        return {"status": "error", "message": "DB error"}, 500

    return {"status": "success", "deleted_alias_id": alias_id}, 200


@app.route('/organizations/<int:organization_id>/merge_preview', methods=['GET'])
def organization_merge_preview(organization_id: int):
    """Side-by-side comparison of two organizations and what merging the first into the
    second (``?target_id=``) would do — read-only. Returns both organizations (name, type,
    description, aliases, document count, bound information source) and ``effects``: the
    alias added, aliases moved, documents moved / present in both, entities renamed and what
    happens to the sources. Backs the confirmation step of every organization merge."""
    from library.organization_source_sync import merge_preview

    target_id = request.args.get('target_id', type=int)
    if target_id is None or target_id < 1:
        return {"status": "error", "message": "target_id is required"}, 400

    session = get_scoped_session()
    try:
        preview = merge_preview(session, organization_id, target_id)
    except LookupError:
        return {"status": "error", "message": "Organization not found"}, 404
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    return jsonify({"status": "success", **preview}), 200


@app.route('/organizations/<int:organization_id>/merge', methods=['POST', 'OPTIONS'])
def organization_merge(organization_id: int):
    """Merge one registry organization into another, without a document context.

    Body: {"target_organization_id": int, "make_global_alias": bool (default
    true)}. Unlike POST /document/<id>/organizations/merge (which starts from
    a document's resolved orgName entity), this is the plain duplicate-cleanup
    path from the /organizations registry browser: two Organization rows for
    the same real-world entity, created because organization_registry does
    exact-match resolution only (no fuzzy auto-merge — see
    docs/organization-ner-alias-plan.md). source is deleted once orphaned
    (organization_registry.merge); the response's organization_id is always
    the surviving (target) row, so the frontend can navigate there."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library import organization_registry
    from library.db.models import Organization

    data = request.get_json(silent=True) or {}
    target_organization_id, error = _entities_doc_id(data.get('target_organization_id'))
    if error:
        return error
    make_global_alias = bool(data.get('make_global_alias', True))

    session = get_scoped_session()
    if session.get(Organization, organization_id) is None:
        return {"status": "error", "message": "Organization not found"}, 404
    if session.get(Organization, target_organization_id) is None:
        return {"status": "error", "message": "Target organization not found"}, 404

    from library.organization_source_sync import merge_organizations

    try:
        # Also folds the information sources of both organizations and renames the entities.
        result = merge_organizations(
            session, organization_id, target_organization_id, make_global_alias=make_global_alias,
        )
        session.commit()
    except organization_registry.AliasConflictError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc),
                "existing_organization_id": exc.existing_organization_id}, 409
    except ValueError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}, 400
    except Exception:
        session.rollback()
        logging.exception("organization merge failed: %s -> %s", organization_id, target_organization_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", **result}), 200


@app.route('/document/<int:doc_id>/organizations/merge', methods=['POST', 'OPTIONS'])
def document_organizations_merge(doc_id: int):
    """Merge an orgName entity of a document into another organization, globally.

    Body: {"source_entity_id": int, "target_entity_id": int OR "target_organization_id": int,
           "make_global_alias": bool (default true), "comment": str|None}.
    source_entity_id must be a document_entities row (entity_type=orgName) of
    this document, already resolved to an organization. Exactly one of
    target_entity_id (another orgName entity of this same document) or
    target_organization_id (any organization from the global registry search,
    GET /organizations?q=) must be given. No embeddings-lock: unlike editing
    document text or refreshing NER, a merge only consolidates existing
    document_entities rows (mention_count/variants) — it never touches
    text_md or invalidates embeddings, so it doesn't require reopening the
    document (see the 2026-07 merge-lock discussion in the entities panel).
    """
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from sqlalchemy import select
    from library import organization_registry
    from library.db.models import DocumentEntity, DocumentOrganization, Organization, OrganizationAlias
    from library.entity_review_audit import record_entity_decision

    data = request.get_json(silent=True) or {}
    source_entity_id, error = _entities_doc_id(data.get('source_entity_id'))
    if error:
        return error
    has_target_entity = data.get('target_entity_id') not in (None, "")
    has_target_organization = data.get('target_organization_id') not in (None, "")
    if has_target_entity == has_target_organization:
        return {"status": "error",
                "message": "give exactly one of target_entity_id, target_organization_id"}, 400
    make_global_alias = bool(data.get('make_global_alias', True))
    comment = (data.get('comment') or "").strip() or None

    session = get_scoped_session()
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    source_entity = session.get(DocumentEntity, source_entity_id)
    if source_entity is None or source_entity.document_id != doc_id or source_entity.entity_type != "orgName":
        return {"status": "error", "message": "source_entity_id must be an orgName entity of this document"}, 400
    source_link = session.execute(select(DocumentOrganization).where(
        DocumentOrganization.document_entity_id == source_entity.id,
    )).scalars().first()
    if source_link is None:
        return {"status": "error", "message": "source_entity_id is not yet a resolved organization"}, 409

    target_entity = None
    if has_target_entity:
        target_entity_id, error = _entities_doc_id(data.get('target_entity_id'))
        if error:
            return error
        if target_entity_id == source_entity_id:
            return {"status": "error", "message": "source_entity_id and target_entity_id must differ"}, 400
        target_entity = session.get(DocumentEntity, target_entity_id)
        if target_entity is None or target_entity.document_id != doc_id or target_entity.entity_type != "orgName":
            return {"status": "error", "message": "target_entity_id must be an orgName entity of this document"}, 400
        target_link = session.execute(select(DocumentOrganization).where(
            DocumentOrganization.document_entity_id == target_entity.id,
        )).scalars().first()
        if target_link is None:
            return {"status": "error", "message": "target_entity_id is not yet a resolved organization"}, 409
        target_organization_id = target_link.organization_id
    else:
        target_organization_id, error = _entities_doc_id(data.get('target_organization_id'))
        if error:
            return error
        target_organization = session.get(Organization, target_organization_id)
        if target_organization is None:
            return {"status": "error", "message": "Target organization not found"}, 404
        if target_organization_id == source_link.organization_id:
            return {"status": "error", "message": "source entity already belongs to this organization"}, 400

    source_entity_text = source_entity.entity_text
    source_entity_variants = list(source_entity.variants or [])
    target_variants_before = list(target_entity.variants or []) if target_entity is not None else []

    from library.organization_source_sync import merge_organizations

    try:
        result = merge_organizations(
            session, source_link.organization_id, target_organization_id,
            make_global_alias=make_global_alias,
        )
        if target_entity is not None:
            # Both entities were already in this document — combine onto the target row.
            target_entity.mention_count += source_entity.mention_count
            combined_variants = dict.fromkeys(target_entity.variants or [])
            for value in [source_entity_text, *source_entity_variants]:
                if value.casefold() != target_entity.entity_text.casefold():
                    combined_variants.setdefault(value)
            target_entity.variants = list(combined_variants)
            session.delete(source_entity)
            surviving_entity = target_entity
        else:
            # Target organization wasn't mentioned in this document yet — the
            # source row survives, renamed to the target's canonical name.
            combined_variants = dict.fromkeys(source_entity.variants or [])
            if source_entity_text.casefold() != result["canonical_name"].casefold():
                combined_variants.setdefault(source_entity_text)
            source_entity.entity_text = result["canonical_name"]
            source_entity.variants = [
                v for v in combined_variants if v.casefold() != result["canonical_name"].casefold()
            ]
            surviving_entity = source_entity
        session.flush()

        alias_id = None
        if make_global_alias:
            alias_row = session.execute(select(OrganizationAlias).where(
                OrganizationAlias.normalized_alias == organization_registry.normalize_alias(source_entity_text),
            )).scalars().first()
            alias_id = alias_row.id if alias_row is not None else None

        record_entity_decision(
            session,
            document_id=doc_id,
            document_entity_id=surviving_entity.id,
            entity_type="orgName",
            entity_text=surviving_entity.entity_text,
            decision="organization_merged",
            comment=comment,
            details={
                "source_entity_text": source_entity_text,
                "target_entity_text": result["canonical_name"],
                "organization_id": result["organization_id"],
                "alias_id": alias_id,
                "global_alias": make_global_alias,
                "source_variants": [source_entity_text, *source_entity_variants],
                "target_variants_before": target_variants_before,
            },
        )
        session.commit()
    except organization_registry.AliasConflictError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc),
                "existing_organization_id": exc.existing_organization_id}, 409
    except Exception:
        session.rollback()
        logging.exception("organization merge failed for document %s", doc_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({
        "status": "success",
        "organization_id": result["organization_id"],
        "canonical_name": result["canonical_name"],
        "mention_count": surviving_entity.mention_count,
        "variants": surviving_entity.variants,
    }), 200


@app.route('/document/<int:doc_id>/places/merge', methods=['POST', 'OPTIONS'])
def document_places_merge(doc_id: int):
    """Merge a place entity of a document into another place entity of the same document.

    Body: {"source_entity_id": int, "target_entity_id": int, "comment": str|None}.
    Both must be document_entities rows of this document. target_entity_id's
    entity_type must be geogName or placeName (the survivor is always a
    place); source_entity_id may additionally be orgName, covering NER
    misclassifications where the same real-world place was tagged orgName in
    one mention and geogName/placeName in another (e.g. "Kijów"). Per-document
    only — unlike orgName, places have no cross-document registry (see
    library/entity_service.py:merge_document_entities). No embeddings-lock:
    a merge only consolidates existing document_entities rows, it never
    touches text_md or invalidates embeddings, so it doesn't require
    reopening the document (see the 2026-07 merge-lock discussion in the
    entities panel; same reasoning as POST /document/<id>/organizations/merge).
    """
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import DocumentEntity
    from library.entity_review_audit import record_entity_decision
    from library.entity_service import MERGEABLE_PLACE_SOURCE_TYPES, PLACE_TYPES, merge_document_entities

    data = request.get_json(silent=True) or {}
    source_entity_id, error = _entities_doc_id(data.get('source_entity_id'))
    if error:
        return error
    target_entity_id, error = _entities_doc_id(data.get('target_entity_id'))
    if error:
        return error
    if source_entity_id == target_entity_id:
        return {"status": "error", "message": "source_entity_id and target_entity_id must differ"}, 400
    comment = (data.get('comment') or "").strip() or None

    session = get_scoped_session()
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    source_entity = session.get(DocumentEntity, source_entity_id)
    if (source_entity is None or source_entity.document_id != doc_id
            or source_entity.entity_type not in MERGEABLE_PLACE_SOURCE_TYPES):
        return {
            "status": "error",
            "message": "source_entity_id must be a geogName/placeName/orgName entity of this document",
        }, 400
    target_entity = session.get(DocumentEntity, target_entity_id)
    if (target_entity is None or target_entity.document_id != doc_id
            or target_entity.entity_type not in PLACE_TYPES):
        return {
            "status": "error",
            "message": "target_entity_id must be a geogName/placeName entity of this document",
        }, 400

    source_entity_text = source_entity.entity_text
    source_entity_type = source_entity.entity_type
    source_variants = list(source_entity.variants or [])

    try:
        merge_document_entities(source_entity, target_entity)
        session.delete(source_entity)
        session.flush()
        # A merged target is source='manual', which place enrichment skips, so a
        # target neither side had geocoded would stay unverified forever. One
        # cached lookup; failures are swallowed inside geocode_single_place().
        geocoded = target_entity.geocode_id is not None
        if not geocoded:
            from library.place_verification import geocode_single_place

            geocoded = geocode_single_place(session, doc, target_entity)["geocoded"]
        record_entity_decision(
            session,
            document_id=doc_id,
            document_entity_id=target_entity.id,
            entity_type=target_entity.entity_type,
            entity_text=target_entity.entity_text,
            decision="place_merged",
            comment=comment,
            details={
                "source_entity_text": source_entity_text,
                "source_entity_type": source_entity_type,
                "source_variants": source_variants,
                "target_entity_text": target_entity.entity_text,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("place merge failed for document %s", doc_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({
        "status": "success",
        "entity_id": target_entity.id,
        "entity_text": target_entity.entity_text,
        "mention_count": target_entity.mention_count,
        "variants": target_entity.variants,
        "geocoded": geocoded,
    }), 200


@app.route('/document/<int:doc_id>/persons/merge', methods=['POST', 'OPTIONS'])
def document_persons_merge(doc_id: int):
    """Fold a person entity of a document into another person entity of the same document.

    Body: {"source_entity_id": int, "target_entity_id": int}. Both are persName rows of this document
    ("Stone" into "Andy Stone"). Counts and surface forms move to the target, the source's registry link is
    re-pointed at the target's person (the mention becomes an alias, so later documents resolve it
    directly) and the decision is audited as ``person_merged`` and replayed after entity refreshes.
    """
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.db.models import DocumentEntity, DocumentPerson, Person
    from library.entity_review_audit import record_entity_decision
    from library.entity_service import merge_document_entities

    data = request.get_json(silent=True) or {}
    source_entity_id, error = _entities_doc_id(data.get('source_entity_id'))
    if error:
        return error
    target_entity_id, error = _entities_doc_id(data.get('target_entity_id'))
    if error:
        return error
    if source_entity_id == target_entity_id:
        return {"status": "error", "message": "source_entity_id and target_entity_id must differ"}, 400

    session = get_scoped_session()
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404
    source = session.get(DocumentEntity, source_entity_id)
    target = session.get(DocumentEntity, target_entity_id)
    if any(row is None or row.document_id != doc_id or row.entity_type != "persName" for row in (source, target)):
        return {"status": "error", "message": "Obie encje muszą być osobami tego dokumentu."}, 400

    source_text, source_variants = source.entity_text, list(source.variants or [])

    def link_of(entity):
        return session.execute(sa_select(DocumentPerson).where(
            DocumentPerson.document_id == doc_id,
            sa_func.lower(DocumentPerson.raw_mention) == entity.entity_text.lower(),
        )).scalars().first()

    try:
        source_link, target_link = link_of(source), link_of(target)
        if source_link is not None:
            if target_link is None:
                person_registry.reject_review_link(session, source_link)
            elif source_link.person_id == target_link.person_id:
                session.delete(source_link)
            else:
                person_registry.merge_review_link(session, source_link, session.get(Person, target_link.person_id))
        merge_document_entities(source, target)
        session.delete(source)
        session.flush()
        record_entity_decision(
            session, document_id=doc_id, document_entity_id=target.id, entity_type="persName",
            entity_text=source_text, decision="person_merged",
            details={"target_entity_text": target.entity_text, "source_variants": source_variants},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("person merge failed for document %s", doc_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "entity_id": target.id, "entity_text": target.entity_text,
                    "mention_count": target.mention_count, "variants": target.variants}), 200


@app.route('/document/<int:doc_id>/products/merge', methods=['POST', 'OPTIONS'])
def document_products_merge(doc_id: int):
    """Fold several product/system entities of a document ("Starlinka", "Starlinek") into one.

    Body: {"entity_ids": [int, ...] (2-20 productName rows of this document), "name": "Starlink"}. The row
    already called ``name`` survives, otherwise the first one is renamed; counts and surface forms of the
    others (and the old name) become its variants. Audited as ``product_merged`` and replayed after entity
    refreshes (library/entity_overrides.py).
    """
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import DocumentEntity
    from library.entity_overrides import merge_product_entities
    from library.entity_review_audit import record_entity_decision

    data = request.get_json(silent=True) or {}
    ids, name = data.get('entity_ids'), data.get('name')
    if not isinstance(ids, list) or not 2 <= len(ids) <= 20 or not all(isinstance(i, int) for i in ids) \
            or len(set(ids)) != len(ids):
        return {"status": "error", "message": "Podaj od 2 do 20 różnych produktów do scalenia."}, 400
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        return {"status": "error", "message": "Nieprawidłowa nazwa produktu."}, 400

    session = get_scoped_session()
    if Document.get_by_id(session, doc_id) is None:
        return {"status": "error", "message": "Document not found"}, 404
    rows = [session.get(DocumentEntity, entity_id) for entity_id in ids]
    if any(row is None or row.document_id != doc_id or row.entity_type != "productName" for row in rows):
        return {"status": "error", "message": "Wszystkie encje muszą być produktami tego dokumentu."}, 400
    sources = list(dict.fromkeys(v for row in rows for v in (row.entity_text, *(row.variants or []))))
    try:
        target = merge_product_entities(session, rows, " ".join(name.split()))
        record_entity_decision(
            session, document_id=doc_id, document_entity_id=target.id, entity_type="productName",
            entity_text=target.entity_text, decision="product_merged", details={"sources": sources},
        )
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("product merge failed for document %s", doc_id)
        return {"status": "error", "message": "Nie udało się scalić produktów."}, 500
    return jsonify({"status": "success", "entity_id": target.id, "entity_text": target.entity_text,
                    "mention_count": target.mention_count, "variants": target.variants}), 200


@app.route('/tags', methods=['GET'])
def tags_list():
    """Distinct tags across documents (CSV column), most used first — editor autocomplete."""
    from sqlalchemy import select as sa_select

    session = get_scoped_session()
    rows = session.execute(
        sa_select(Document.tags).where(Document.tags.isnot(None))
    ).scalars().all()
    counts: dict[str, int] = {}
    for tags in rows:
        for tag in (tags or "").split(","):
            tag = tag.strip()
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"status": "success", "tags": [{"tag": t, "count": c} for t, c in ordered]}, 200


def _source_dict(row, count: int = 0, tools: list | None = None, persons: list | None = None):
    # "source" duplicates "name" for backward compatibility (editor autocomplete
    # consumed the old distinct-values shape).
    from library import knowledge_sources

    return {
        "id": row.id, "name": row.name, "source": row.name,
        "description": row.description, "url": row.url,
        "is_active": row.is_active, "count": count,
        **knowledge_sources.source_fields(row),
        "tools": tools or [],
        "persons": persons or [],
    }


def _source_doc_count(session, source_id: int) -> int:
    from sqlalchemy import func as sa_func, select as sa_select

    return session.execute(
        sa_select(sa_func.count()).where(Document.discovery_source_id == source_id)
    ).scalar_one()


@app.route('/sources', methods=['GET'])
def sources_list():
    """Sources lookup with per-source document counts, most used first.

    ?active=1 limits to is_active sources (editor/extension pickers)."""
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import DiscoverySource

    session = get_scoped_session()
    counts = (
        sa_select(Document.discovery_source_id.label("source_id"), sa_func.count().label("cnt"))
        .where(Document.discovery_source_id.isnot(None))
        .group_by(Document.discovery_source_id)
        .subquery()
    )
    doc_count = sa_func.coalesce(counts.c.cnt, 0)
    query = sa_select(DiscoverySource, doc_count).outerjoin(
        counts, counts.c.source_id == DiscoverySource.id)
    if request.args.get('active') in ('1', 'true', 'yes'):
        query = query.where(DiscoverySource.is_active.is_(True))
    rows = session.execute(query.order_by(doc_count.desc(), DiscoverySource.name)).all()
    from library import knowledge_sources

    tools = knowledge_sources.tools_for_sources(session)
    persons = knowledge_sources.persons_for_sources(session)
    return {"status": "success",
            "sources": [_source_dict(row, count, tools.get(row.id), persons.get(row.id)) for row, count in rows]}, 200


@app.route('/sources', methods=['POST', 'OPTIONS'])
def sources_add():
    """Add a discovery source. Body (JSON): {"name": "...", "description": "...",
    "url": "...", "is_active": true}. Only name is required."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import DiscoverySource

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or "").strip()
    if not name:
        return {"status": "error", "message": "name is required"}, 400

    from library import knowledge_sources

    try:
        extra = knowledge_sources.validate_fields(data)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400

    session = get_scoped_session()
    row = DiscoverySource(name=name,
                 description=(data.get('description') or "").strip() or None,
                 is_active=bool(data.get('is_active', True)))
    for field, value in extra.items():
        setattr(row, field, value)
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("source add failed for %r", name)
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    # jsonify enforces Content-Type: application/json (CodeQL py/reflective-xss)
    return jsonify({"status": "success", "source": _source_dict(row)}), 200


@app.route('/sources/<int:source_id>', methods=['PATCH', 'OPTIONS'])
def sources_update(source_id: int):
    """Update a source. Documents reference the row by id
    (discovery_source_id), so renaming only edits this row — every document
    follows the new name automatically."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import DiscoverySource

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(DiscoverySource, source_id)
    if row is None:
        return {"status": "error", "message": "Source not found"}, 404

    if 'name' in data:
        name = (data.get('name') or "").strip()
        if not name:
            return {"status": "error", "message": "name cannot be empty"}, 400
        row.name = name
    if 'description' in data:
        row.description = (data.get('description') or "").strip() or None
    from library import knowledge_sources

    try:
        extra = knowledge_sources.validate_fields(data)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    for field, value in extra.items():  # includes url, kind, status, dates, rating, review note, note path
        setattr(row, field, value)
    if 'is_active' in data:
        row.is_active = bool(data.get('is_active'))

    try:
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("source update failed for %s", source_id)
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    return jsonify({"status": "success",
                    "source": _source_dict(row, _source_doc_count(session, row.id))}), 200


@app.route('/sources/<int:source_id>', methods=['DELETE', 'OPTIONS'])
def sources_delete(source_id: int):
    """Delete an unused source. Sources with documents return 409 — deactivate
    them instead (is_active=false) so document history stays intact."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import DiscoverySource

    session = get_scoped_session()
    row = session.get(DiscoverySource, source_id)
    if row is None:
        return {"status": "error", "message": "Source not found"}, 404
    used_by = _source_doc_count(session, row.id)
    if used_by > 0:
        return jsonify({"status": "error",
                        "message": f"Source is used by {used_by} documents — deactivate it instead"}), 409
    from library import knowledge_sources

    linked = knowledge_sources.link_count(session, row.id)
    if linked > 0:
        return jsonify({"status": "error",
                        "message": f"Source is linked to {linked} tools/people — deactivate it instead"}), 409
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("source delete failed for %s", source_id)
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": source_id}), 200


@app.route('/languages', methods=['GET'])
def languages_list():
    """Languages currently used by at least one document, most used first.

    documents.language is free text, not FK'd to the languages table (see
    Language model docstring) — this backs the /search languages filter
    picker. An inner join against actual usage on purpose: a language that
    no document has (any more) would otherwise show up as a checkbox that
    always returns zero results — the languages table is a superset of
    codes ever seen, not a set of "selectable" values."""
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import Language

    session = get_scoped_session()
    counts = (
        sa_select(Document.language.label("code"), sa_func.count().label("cnt"))
        .where(Document.language.isnot(None))
        .group_by(Document.language)
        .subquery()
    )
    query = sa_select(Language, counts.c.cnt).join(counts, counts.c.code == Language.code)
    rows = session.execute(query.order_by(counts.c.cnt.desc(), Language.code)).all()
    return {"status": "success", "languages": [
        {"code": row.code, "name_pl": row.name_pl, "count": count} for row, count in rows
    ]}, 200


def _exclusion_dict(row):
    return {
        "id": row.id, "entity_text": row.entity_text, "entity_type": row.entity_type,
        "scope": row.scope, "author": row.author, "document_id": row.document_id, "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.route('/ner_exclusions', methods=['GET'])
def ner_exclusions_list():
    """NER exclusion dictionary — false positives suppressed at entity refresh."""
    from sqlalchemy import select as sa_select
    from library.db.models import NerExclusion

    session = get_scoped_session()
    rows = session.execute(
        sa_select(NerExclusion).order_by(NerExclusion.created_at.desc())
    ).scalars().all()
    return {"status": "success", "count": len(rows),
            "exclusions": [_exclusion_dict(r) for r in rows]}, 200


@app.route('/ner_exclusions', methods=['POST', 'OPTIONS'])
def ner_exclusions_add():
    """Add an exclusion rule. Body (JSON): {"entity_text": "...", "entity_type": "persName"|...|"*",
    "scope": "global"|"author"|"document", "author": "..."|null, "document_id": <id>, "note": "..."}.
    For scope=author without an explicit author, the author is taken from document_id;
    scope=document requires document_id and applies to that document only."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import NerExclusion

    data = request.get_json(silent=True) or {}
    entity_text = (data.get('entity_text') or "").strip()
    if not entity_text:
        return {"status": "error", "message": "entity_text is required"}, 400
    entity_type = (data.get('entity_type') or "*").strip()
    if entity_type not in ("*", "persName", "orgName", "geogName", "placeName"):
        return {
            "status": "error",
            "message": "entity_type must be persName, orgName, geogName, placeName or *",
        }, 400
    scope = (data.get('scope') or "global").strip()
    if scope not in ("global", "author", "document"):
        return {"status": "error", "message": "scope must be global, author or document"}, 400

    session = get_scoped_session()
    author = (data.get('author') or "").strip() or None
    exclusion_document_id = None
    if scope == "document":
        exclusion_document_id, error = _entities_doc_id(data.get('document_id'))
        if error:
            return {"status": "error", "message": "scope=document requires document_id"}, 400
        if Document.get_by_id(session, exclusion_document_id) is None:
            return {"status": "error", "message": "Document not found"}, 404
    if scope == "author" and author is None:
        doc_id, error = _entities_doc_id(data.get('document_id'))
        if error:
            return {"status": "error",
                    "message": "scope=author requires author or document_id"}, 400
        doc = Document.get_by_id(session, doc_id)
        if doc is None:
            return {"status": "error", "message": "Document not found"}, 404
        author = (doc.byline or "").strip() or None
        if author is None:
            return {"status": "error", "message": "Document has no author to scope the exclusion to"}, 400

    row = NerExclusion(entity_text=entity_text, entity_type=entity_type, scope=scope,
                       author=author if scope == "author" else None,
                       document_id=exclusion_document_id,
                       note=(data.get('note') or "").strip() or None)
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("ner_exclusion add failed for %r", entity_text)
        return {"status": "error", "message": "DB error (duplicate rule?)"}, 409

    return {"status": "success", "exclusion": _exclusion_dict(row)}, 200


@app.route('/ner_exclusions/<int:exclusion_id>', methods=['DELETE', 'OPTIONS'])
def ner_exclusions_delete(exclusion_id: int):
    """Remove an exclusion rule — the entity will be detected again on the next refresh."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import NerExclusion

    session = get_scoped_session()
    row = session.get(NerExclusion, exclusion_id)
    if row is None:
        return {"status": "error", "message": "Exclusion not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("ner_exclusion delete failed for %s", exclusion_id)
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": exclusion_id}), 200


def _correction_dict(row):
    return {
        "id": row.id, "match_lemma": row.match_lemma, "match_entity_type": row.match_entity_type,
        "corrected_text": row.corrected_text, "corrected_entity_type": row.corrected_entity_type,
        "scope": row.scope, "author": row.author, "reason": row.reason, "approved_by": row.approved_by,
        "source_document_id": row.source_document_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.route('/ner_corrections', methods=['GET'])
def ner_corrections_list():
    """NER correction dictionary (Faza 6) — human-approved lemma-keyed display-name fixes."""
    from sqlalchemy import select as sa_select
    from library.db.models import NerCorrection

    session = get_scoped_session()
    rows = session.execute(
        sa_select(NerCorrection).order_by(NerCorrection.created_at.desc())
    ).scalars().all()
    return {"status": "success", "count": len(rows),
            "corrections": [_correction_dict(r) for r in rows]}, 200


@app.route('/ner_context_decisions', methods=['GET'])
def ner_context_decisions():
    """Browse automatic NER verdicts without modifying their history."""
    from library.ner_decisions import list_decisions, parse_decision_filters

    try:
        filters = parse_decision_filters(request.args)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    return {"status": "success", **list_decisions(get_scoped_session(), **filters)}, 200


@app.route('/ner_corrections/stats', methods=['GET'])
def ner_corrections_stats():
    """Usage statistics of the NER correction dictionary: per rule how many times it fired and in how
    many documents (ner_correction_applications), unused rules, application counts per type change and
    the number of exclusion rules — shows which mistakes recur and deserve a code fix."""
    from library.ner_corrections import corrections_stats

    session = get_scoped_session()
    return {"status": "success", **corrections_stats(session)}, 200


@app.route('/ner_corrections', methods=['POST', 'OPTIONS'])
def ner_corrections_add():
    """Approve a correction rule. Body (JSON): {"match_lemma": "...", "corrected_text": "...",
    "match_entity_type": "persName"|...|"*" (default "*"), "corrected_entity_type": "..."|null,
    "scope": "global"|"author", "author": "..."|null, "reason": "...", "approved_by": "...",
    "source_document_id": <id>|null, "document_id": <id>}. reason and approved_by are required —
    this is the decision log: why the correction was approved and by whom. For scope=author
    without an explicit author, the author is taken from document_id."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import NerCorrection

    data = request.get_json(silent=True) or {}
    match_lemma = (data.get('match_lemma') or "").strip()
    if not match_lemma:
        return {"status": "error", "message": "match_lemma is required"}, 400
    corrected_text = (data.get('corrected_text') or "").strip()
    if not corrected_text:
        return {"status": "error", "message": "corrected_text is required"}, 400
    reason = (data.get('reason') or "").strip()
    if not reason:
        return {"status": "error", "message": "reason is required (decision log)"}, 400
    approved_by = (data.get('approved_by') or "").strip()
    if not approved_by:
        return {"status": "error", "message": "approved_by is required (decision log)"}, 400

    match_entity_type = (data.get('match_entity_type') or "*").strip()
    if match_entity_type not in ("*", "persName", "orgName", "geogName", "placeName"):
        return {
            "status": "error",
            "message": "match_entity_type must be persName, orgName, geogName, placeName or *",
        }, 400
    corrected_entity_type = (data.get('corrected_entity_type') or "").strip() or None
    if corrected_entity_type is not None and corrected_entity_type not in ("persName", "orgName", "geogName", "placeName"):
        return {
            "status": "error",
            "message": "corrected_entity_type must be persName, orgName, geogName or placeName",
        }, 400
    scope = (data.get('scope') or "global").strip()
    if scope not in ("global", "author"):
        return {"status": "error", "message": "scope must be global or author"}, 400

    session = get_scoped_session()
    author = (data.get('author') or "").strip() or None
    source_document_id, error = _entities_doc_id(data.get('source_document_id')) \
        if data.get('source_document_id') is not None else (None, None)
    if error:
        return error
    if scope == "author" and author is None:
        doc_id, error = _entities_doc_id(data.get('document_id'))
        if error:
            return {"status": "error",
                    "message": "scope=author requires author or document_id"}, 400
        doc = Document.get_by_id(session, doc_id)
        if doc is None:
            return {"status": "error", "message": "Document not found"}, 404
        author = (doc.byline or "").strip() or None
        if author is None:
            return {"status": "error", "message": "Document has no author to scope the correction to"}, 400

    row = NerCorrection(
        match_lemma=match_lemma, match_entity_type=match_entity_type,
        corrected_text=corrected_text, corrected_entity_type=corrected_entity_type,
        scope=scope, author=author if scope == "author" else None,
        reason=reason, approved_by=approved_by, source_document_id=source_document_id,
    )
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("ner_correction add failed for %r", match_lemma)
        return {"status": "error", "message": "DB error (duplicate rule?)"}, 409

    return {"status": "success", "correction": _correction_dict(row)}, 200


@app.route('/ner_corrections/<int:correction_id>', methods=['DELETE', 'OPTIONS'])
def ner_corrections_delete(correction_id: int):
    """Remove a correction rule — past applications stay in the audit log (ner_correction_applications)."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import NerCorrection

    session = get_scoped_session()
    row = session.get(NerCorrection, correction_id)
    if row is None:
        return {"status": "error", "message": "Correction not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("ner_correction delete failed for %s", correction_id)
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": correction_id}), 200


@app.route('/ner_correction_applications', methods=['GET'])
def ner_correction_applications_list():
    """Audit log of every time a NerCorrection rule actually fired.
    Optional query params: document_id=<id>, correction_id=<id>."""
    from sqlalchemy import select as sa_select
    from library.db.models import NerCorrectionApplication

    session = get_scoped_session()
    query = sa_select(NerCorrectionApplication)
    document_id_raw = request.args.get('document_id')
    if document_id_raw is not None:
        document_id, error = _entities_doc_id(document_id_raw)
        if error:
            return error
        query = query.where(NerCorrectionApplication.document_id == document_id)
    correction_id_raw = request.args.get('correction_id')
    if correction_id_raw is not None:
        try:
            correction_id = int(correction_id_raw)
        except ValueError:
            return {"status": "error", "message": "correction_id must be an integer"}, 400
        query = query.where(NerCorrectionApplication.correction_id == correction_id)
    query = query.order_by(NerCorrectionApplication.applied_at.desc())

    rows = session.execute(query).scalars().all()
    return {"status": "success", "count": len(rows), "applications": [
        {
            "id": r.id, "document_id": r.document_id, "correction_id": r.correction_id,
            "entity_type_before": r.entity_type_before, "entity_text_before": r.entity_text_before,
            "entity_type_after": r.entity_type_after, "entity_text_after": r.entity_text_after,
            "applied_at": r.applied_at.isoformat() if r.applied_at else None,
        }
        for r in rows
    ]}, 200


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
    repo = DocumentRepository(session)
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


# /website_similar was removed in stage 12 of the search rebuild — POST /search
# (library/search_routes.py) is the only search endpoint; its explicit variant
# ({"query": ..., "limit": ...}) runs the same hybrid ranking without the LLM.


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
    """Fetch YouTube captions for a document that has no transcript yet.

    URL_ADDED is a first attempt; TEMPORARY_ERROR/NEED_TRANSCRIPTION are retries.
    The endpoint name is retained for API compatibility.
    """
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

    # A video imported with a "ready" default state (feed default_state) has no
    # transcript at all; an empty text is what makes a fetch legitimate there.
    no_transcript_yet = (
        doc.processing_status == StalkerDocumentStatus.READY_FOR_EMBEDDING.name
        and not (doc.text or "").strip()
    )
    if doc.processing_status not in _YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES and not no_transcript_yet:
        return {
            "status": "error",
            "message": f"Document is in state '{doc.processing_status}' — captions retry is only allowed "
                       f"before a transcript has been captured ({', '.join(sorted(_YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES))}, "
                       f"or {StalkerDocumentStatus.READY_FOR_EMBEDDING.name} with an empty text)",
        }, 409

    first_attempt = doc.processing_status in (
        StalkerDocumentStatus.URL_ADDED.name, StalkerDocumentStatus.READY_FOR_EMBEDDING.name,
    )
    webshare_api_key = cfg.get("WEBSHARE_API_KEY")
    updated = process_youtube_url(
        session=session,
        youtube_url=doc.url,
        language=doc.language,
        chapter_list=doc.chapter_list,
        note=doc.note,
        source=doc.discovery_source_name,
        webshare_api_key=webshare_api_key,
    )

    return {
        "status": "success",
        "message": "Captions fetch finished" if first_attempt else "Captions retry finished",
        "id": updated.id,
        "processing_status": updated.processing_status,
        "processing_error_code": updated.processing_error_code,
    }, 200


@app.route('/website_youtube_refetch_description', methods=['POST'])
def website_youtube_refetch_description():
    """Re-fetch a YouTube document's description and auto-parsed chapter list from yt-dlp.

    Unlike the metadata fetch during ingest (which only ever runs once, at
    URL_ADDED — see youtube_processing.py), this can be triggered manually at
    any point in a document's lifecycle. Needed for documents imported while
    pytubefix was silently failing to fetch metadata (PR #561) — captions
    still came through fine since that's a separate library, only
    description/chapter_list/byline/length were left empty.
    """
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
        return {"status": "error", "message": "Description refetch is only available for YouTube documents"}, 400

    cache_dir = os.path.join(cfg.get("CACHE_DIR") or "tmp", "youtube_to_text")
    youtube_file = StalkerYoutubeFile(youtube_url=doc.url, media_type="video", cache_directory=cache_dir)

    if not youtube_file.metadata_available:
        return {
            "status": "error",
            "message": "Nie udało się pobrać metadanych z YouTube (yt-dlp)",
        }, 502

    doc.video_description = youtube_file.description
    parsed_chapters = parse_chapters_from_description(youtube_file.description) if youtube_file.description else None
    if parsed_chapters:
        doc.chapter_list = parsed_chapters
    session.commit()

    return {
        "status": "success",
        "message": f"Znaleziono {len(parsed_chapters.splitlines())} rozdziałów w opisie" if parsed_chapters
                   else "Opis zapisany, nie znaleziono listy rozdziałów",
        "id": doc.id,
        "video_description": doc.video_description,
        "chapter_list": doc.chapter_list,
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


@app.route('/website_delete', methods=['DELETE'])
def website_delete():
    link_id = request.args.get('id')
    if link_id is None:
        data = request.get_json(silent=True)
        link_id = data.get('id') if isinstance(data, dict) else None
    if (isinstance(link_id, bool) or len(str(link_id)) > 10
            or not str(link_id).isascii() or not str(link_id).isdigit()):
        return {"status": "error", "message": "id must be a positive integer"}, 400
    link_id = int(link_id)
    if not 0 < link_id <= 2147483647:
        return {"status": "error", "message": "id must be a positive integer"}, 400

    session = get_scoped_session()
    service = DocumentService(session)
    try:
        deleted = service.delete_document(int(link_id))
        if not deleted:
            session.rollback()
            return {"status": "success", "message": "Page doesn't exist in database", "encoding": "utf8"}, 200
        return {"status": "success", "message": "Page has been deleted from database", "encoding": "utf8"}, 200
    except Exception as e:
        session.rollback()
        logging.error("Failed to delete document: %s", e)
        return {"status": "error", "message": "Failed to delete document"}, 500


@app.route('/document/<int:document_id>/email_footer_rule', methods=['GET', 'POST', 'DELETE'])
def email_footer_rule(document_id: int):
    """Read, create, or remove the one footer rule scoped to an email sender."""
    session = get_scoped_session()
    doc = session.get(Document, document_id)
    if doc is None or doc.document_type != StalkerDocumentType.email.name:
        return {"status": "error", "message": "Email document not found"}, 404

    if request.method in ('GET', 'HEAD'):
        sender = normalize_sender_email(doc.email_sender)
        rule = session.scalar(select(EmailFooterRule).where(EmailFooterRule.sender_email == sender)) if sender else None
        return {
            "status": "success",
            "email_sender": sender,
            "footer_text": rule.footer_text if rule else None,
        }, 200

    if request.method == 'DELETE':
        sender = normalize_sender_email(doc.email_sender)
        if not sender:
            return {"status": "error", "message": "Email has no sender address"}, 400
        rule = session.scalar(select(EmailFooterRule).where(EmailFooterRule.sender_email == sender))
        if rule is not None:
            session.delete(rule)
            session.commit()
        return {"status": "success"}, 200

    data = request.get_json(silent=True) or {}
    sender = normalize_sender_email(data.get("email_sender") or doc.email_sender)
    footer = (data.get("footer_text") or "").strip()
    current_text = doc.text or ""
    if not sender:
        return {"status": "error", "message": "Podaj poprawny adres nadawcy e-maila."}, 400
    if not footer:
        return {"status": "error", "message": "Zaznacz niepustą stopkę."}, 400
    if not current_text.rstrip().endswith(footer):
        return {"status": "error", "message": "Stopka musi być końcowym fragmentem wiadomości."}, 400

    rule = session.scalar(select(EmailFooterRule).where(EmailFooterRule.sender_email == sender))
    if rule is None:
        rule = EmailFooterRule(sender_email=sender, footer_text=footer)
        session.add(rule)
    else:
        rule.footer_text = footer
    doc.email_sender = sender
    doc.text = apply_footer_rule(session, sender, current_text)
    doc.document_length = len(doc.text or "")
    session.commit()
    return {"status": "success", "email_sender": sender, "text": doc.text}, 200


@app.route('/document/<int:document_id>/search_terms/generate', methods=['POST'])
def generate_document_search_terms(document_id: int):
    """Generate retrieval phrases without overwriting a reviewed value by default."""
    session = get_scoped_session()
    doc = session.get(Document, document_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    data = request.get_json(silent=True) or {}
    replace = bool(data.get("replace", False))
    if (doc.search_terms or "").strip() and not replace:
        return {"status": "success", "search_terms": doc.search_terms, "generated": False}, 200
    text = (doc.text_md or doc.text or "").strip()
    if not text:
        return {"status": "error", "message": "Document has no usable text"}, 400

    from library.search_terms import generate_search_terms

    terms = generate_search_terms(text, doc.title or "")
    if not terms:
        return {"status": "error", "message": "Could not generate search terms"}, 502
    doc.search_terms = ", ".join(terms)
    session.commit()
    return {"status": "success", "search_terms": doc.search_terms, "generated": True}, 200


@app.route('/website_save', methods=['POST'])
def website_save():
    url = request.form.get('url')
    if not url:
        return {"status": "error", "message": "Missing data. Make sure you provide 'url'"}, 400

    link_id = request.form.get('id')
    attrs = {}
    for attr in (
        'text', 'text_md', 'title', 'language', 'tags', 'search_terms', 'summary',
        'outline_md', 'source', 'byline', 'email_sender', 'note',
    ):
        value = request.form.get(attr)
        if value is not None:
            attrs[attr] = value

    if 'outline_anchors' in request.form:
        from library.outline_boundaries import validate_anchor_payload

        raw_anchors = request.form['outline_anchors']
        try:
            payload = json.loads(raw_anchors) if raw_anchors else None
            attrs['outline_anchors'] = None if payload is None else validate_anchor_payload(payload)
        except ValueError as exc:
            return {"status": "error", "message": f"Invalid outline_anchors: {exc}"}, 400

    session = get_scoped_session()
    service = DocumentService(session)
    try:
        if link_id:
            from library.document_editing import document_has_embeddings

            existing = session.get(Document, int(link_id))
            requested_status = request.form.get('processing_status')
            if (
                existing is not None
                and existing.document_type == StalkerDocumentType.youtube.name
                and requested_status == StalkerDocumentStatus.READY_FOR_EMBEDDING.name
                and not (attrs.get("text") if "text" in attrs else existing.text)
            ):
                return {
                    "status": "error",
                    "message": "YouTube document has no transcript. Fetch captions before marking it ready.",
                }, 409
            if existing is not None and document_has_embeddings(session, existing.id):
                content_changed = any(
                    key in attrs and attrs[key] != (getattr(existing, key) or "")
                    for key in ("text", "text_md")
                )
                status_changed = bool(requested_status and requested_status != existing.processing_status)
                if content_changed or status_changed:
                    return {
                        "status": "error",
                        "message": "Document has embeddings. Reopen it for editing before changing content.",
                    }, 409
        doc = service.save_document(
            url=url,
            link_id=int(link_id) if link_id else None,
            processing_status=request.form.get('processing_status'),
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
