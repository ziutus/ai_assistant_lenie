from flask import Flask, Response, g, request, abort, jsonify
from flask_cors import CORS
import logging

from library.config_loader import load_config
from library.db.engine import get_scoped_session
from library.db.models import TranscriptionLog, Document
from library.document_service import DocumentService, ExistingDocumentError
from library.search_service import SearchService
from library.document_repository import DocumentRepository
from library.website.website_paid import website_is_paid
from library.ai_intent_parser import parse_intent
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_type import StalkerDocumentType
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.api_key_routes import bp as api_key_bp
from library.auth import resolve_api_key
from library.chunk_review_routes import bp as chunk_review_bp, start_analysis_worker
from library.llm_cost_routes import bp as llm_cost_bp
from library.reader_routes import bp as reader_bp
from library.search_routes import bp as search_bp
from library.stats_routes import bp as stats_bp
from library.youtube_processing import process_youtube_url

logging.basicConfig(level=logging.INFO)

cfg = load_config()

secrets_backend = cfg.require("SECRETS_BACKEND", "env")

APP_VERSION = "0.3.15.5"
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
app.register_blueprint(llm_cost_bp)
app.register_blueprint(reader_bp)
app.register_blueprint(api_key_bp)
app.register_blueprint(search_bp)
app.register_blueprint(stats_bp)
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
        operation = url_data.get("operation", "create")
        if operation not in {"create", "fill_missing_html"}:
            raise ValueError("Invalid operation")
        if operation == "fill_missing_html":
            doc = service.fill_missing_source_html(
                url=url_data.get("url", ""),
                html=url_data.get("html", ""),
                text=url_data.get("text", ""),
            )
        else:
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

    except ExistingDocumentError as e:
        doc = e.document
        return {
            'status': 'already_exists',
            'message': f'Document already exists with ID: {doc.id}',
            'document_id': doc.id,
            'missing_raw_html': not bool(doc.text_raw),
        }, 409
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
    processing_status = request.args.get('processing_status', 'ALL')
    search_in_documents = request.args.get('search_in_document', '')
    only_missing_obsidian_notes = request.args.get('only_missing_obsidian_notes', '').lower() in ('1', 'true')
    only_has_obsidian_notes = request.args.get('only_has_obsidian_notes', '').lower() in ('1', 'true')
    without_embedding = request.args.get('without_embedding', '').lower() in ('1', 'true')
    try:
        limit = min(max(int(request.args.get('limit', 100)), 1), 100)
        page = max(int(request.args.get('page', 1)), 1)
    except (TypeError, ValueError):
        return {"status": "error", "message": "limit and page must be integers"}, 400
    logging.debug(document_type)

    session = get_scoped_session()
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
    }
    websites_list = repo.get_list(**list_kwargs)
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
    from library.db.models import DocumentChunk, DocumentEmbedding

    result = doc.dict()
    result["embeddings_count"] = session.execute(
        sa_select(sa_func.count()).select_from(DocumentEmbedding)
        .where(DocumentEmbedding.document_id == link_id_int)
    ).scalar()
    result["approved_chunks_count"] = session.execute(
        sa_select(sa_func.count()).select_from(DocumentChunk)
        .where(DocumentChunk.document_id == link_id_int,
               DocumentChunk.type == "TEMAT",
               DocumentChunk.status == "approved")
    ).scalar()
    return result, 200


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
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    return {
        "status": "success",
        "id": doc_id,
        "entities": get_document_entities(session, doc_id),
        "ner_unavailable_at": doc.ner_unavailable_at.isoformat() if doc.ner_unavailable_at else None,
    }, 200


@app.route('/website_entities', methods=['POST'])
def website_entities_refresh():
    """Re-run NER on the document text, verify places and replace stored entities.

    First call after an ner_service restart can take up to ~90s (model load) —
    see ner_service/README.md. Place verification (geocoder + LLM relevance,
    stage 3) runs after the refresh and adds miejsce-* tags to the document;
    its failure does not fail the request.
    """
    from library.entity_service import get_document_entities, refresh_document_entities
    from library.ner_client import NERServiceUnavailable

    doc_id, error = _entities_doc_id(request.form.get('id') or (request.get_json(silent=True) or {}).get('id'))
    if error:
        return error

    session = get_scoped_session()
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        return {"status": "error", "message": "Document not found"}, 404

    text = doc.text_md or doc.text or ""
    if not text.strip():
        return {"status": "error", "message": "Document has no text content"}, 400

    try:
        rows = refresh_document_entities(session, doc_id, text)
    except NERServiceUnavailable:
        # refresh_document_entities already committed doc.ner_unavailable_at.
        return {
            "status": "error",
            "message": "Serwis NER jest niedostępny — spróbuj ponownie za chwilę.",
            "ner_unavailable": True,
        }, 503
    session.commit()

    place_tags: list[str] = []
    persons_linked = 0
    pipelines: list[str] = []
    if rows:
        try:
            from library.place_verification import verify_document_places
            from library.llm_usage.context import llm_usage_context

            with llm_usage_context(document_id=doc_id):
                summary = verify_document_places(session, doc, text)
            session.commit()
            place_tags = summary["tagged"]
        except Exception:
            session.rollback()
            logging.exception("place verification failed for doc %s", doc_id)

        try:
            from library.person_registry import resolve_document_persons
            from library.llm_usage.context import llm_usage_context

            with llm_usage_context(document_id=doc_id):
                p_summary = resolve_document_persons(session, doc, text)
            session.commit()
            persons_linked = len(p_summary["linked"])
        except Exception:
            session.rollback()
            logging.exception("person resolution failed for doc %s", doc_id)

        try:
            from library.overpass_client import attach_document_pipelines

            i_summary = attach_document_pipelines(session, doc_id)
            session.commit()
            pipelines = i_summary["resolved"]
        except Exception:
            session.rollback()
            logging.exception("pipeline lookup failed for doc %s", doc_id)

    return {
        "status": "success",
        "id": doc_id,
        "refreshed": len(rows),
        "place_tags": place_tags,
        "persons_linked": persons_linked,
        "pipelines": pipelines,
        "entities": get_document_entities(session, doc_id),
    }, 200


@app.route('/persons', methods=['GET'])
def persons_search():
    """Search the person registry (NER stage 4) — fuzzy by name/alias (?q=), or list newest."""
    from sqlalchemy import func as sa_func, select as sa_select
    from library.db.models import Person, PersonAlias

    session = get_scoped_session()
    query = (request.args.get('q') or "").strip()
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
    else:
        persons = session.execute(
            sa_select(Person).order_by(Person.created_at.desc()).limit(50)
        ).scalars().all()

    return {
        "status": "success",
        "persons": [
            {
                "id": p.id, "uuid": p.uuid, "canonical_name": p.canonical_name,
                "wikidata_qid": p.wikidata_qid, "description": p.description,
                "aliases": [a.alias for a in p.aliases],
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
    return {
        "status": "success",
        "person": {"id": person.id, "canonical_name": person.canonical_name,
                   "description": person.description, "wikidata_qid": person.wikidata_qid},
        "documents": documents,
    }, 200


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
        .order_by(InformationSource.canonical_name)
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
    rows = session.execute(statement).all()
    entries = [{
        "id": source.id,
        "canonical_name": source.canonical_name,
        "source_type": source.source_type,
        "domain": source.domain,
        "description": source.description,
        "aliases": [alias.alias for alias in source.aliases],
        "document_count": count,
    } for source, count in rows]
    return {"status": "success", "count": len(entries), "entries": entries}, 200


@app.route('/information_sources/<int:source_id>/documents', methods=['GET'])
def information_source_documents(source_id: int):
    """Return documents attributed to one source, optionally filtered by role."""
    from sqlalchemy import select
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
    links = session.scalars(statement).all()
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
        "count": len(entries),
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


def _decide_person_link(link_id: int, require_review: bool):
    """Shared handler for person-link decisions (approve/reject/merge).

    require_review=True is the /persons_review queue semantics (409 outside
    the queue); False is the editor path — lets the user undo a wrong
    wikidata/alias match on any link.
    """
    from library import person_registry
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

    try:
        if action == "approve":
            result = person_registry.approve_review_link(session, link)
        elif action == "reject":
            result = person_registry.reject_review_link(session, link)
        else:
            target_id, error = _entities_doc_id(data.get('target_person_id'))
            if error:
                return error
            target = session.get(Person, target_id)
            if target is None:
                return {"status": "error", "message": "Target person not found"}, 404
            result = person_registry.merge_review_link(session, link, target)
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


@app.route('/website_entities/<int:entity_id>', methods=['DELETE', 'OPTIONS'])
def website_entities_delete(entity_id: int):
    """Delete a stored NER entity row (editor UI).

    For persName entities the matching document_persons link (same document,
    raw_mention == entity_text) is removed too; a person left with no links
    is dropped from the registry."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from sqlalchemy import func as sa_func, select as sa_select
    from library import person_registry
    from library.db.models import DocumentEntity, DocumentPerson

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
        session.delete(entity)
        session.commit()
    except Exception:
        session.rollback()
        logging.exception("entity delete failed for entity %s", entity_id)
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "deleted_entity_id": entity_id,
                    "person_link_removed": link_result is not None,
                    "person_deleted": bool(link_result and link_result.get("person_deleted"))}), 200


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


def _source_dict(row, count: int = 0):
    # "source" duplicates "name" for backward compatibility (editor autocomplete
    # consumed the old distinct-values shape).
    return {
        "id": row.id, "name": row.name, "source": row.name,
        "description": row.description, "url": row.url,
        "is_active": row.is_active, "count": count,
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
    return {"status": "success",
            "sources": [_source_dict(row, count) for row, count in rows]}, 200


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

    session = get_scoped_session()
    row = DiscoverySource(name=name,
                 description=(data.get('description') or "").strip() or None,
                 url=(data.get('url') or "").strip() or None,
                 is_active=bool(data.get('is_active', True)))
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
    if 'url' in data:
        row.url = (data.get('url') or "").strip() or None
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
        "scope": row.scope, "author": row.author, "note": row.note,
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
    "scope": "global"|"author", "author": "..."|null, "document_id": <id>, "note": "..."}.
    For scope=author without an explicit author, the author is taken from document_id."""
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200

    from library.db.models import NerExclusion

    data = request.get_json(silent=True) or {}
    entity_text = (data.get('entity_text') or "").strip()
    if not entity_text:
        return {"status": "error", "message": "entity_text is required"}, 400
    entity_type = (data.get('entity_type') or "*").strip()
    if entity_type not in ("*", "persName", "geogName", "placeName"):
        return {"status": "error", "message": "entity_type must be persName, geogName, placeName or *"}, 400
    scope = (data.get('scope') or "global").strip()
    if scope not in ("global", "author"):
        return {"status": "error", "message": "scope must be global or author"}, 400

    session = get_scoped_session()
    author = (data.get('author') or "").strip() or None
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
    """Retry downloading YouTube captions for a document stuck in a no-transcript
    state (e.g. processing_error_code=CAPTIONS_FETCH_ERROR)."""
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

    if doc.processing_status not in _YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES:
        return {
            "status": "error",
            "message": f"Document is in state '{doc.processing_status}' — captions retry is only allowed "
                       f"before a transcript has been captured ({', '.join(sorted(_YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES))})",
        }, 409

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
        "message": "Captions retry finished",
        "id": updated.id,
        "processing_status": updated.processing_status,
        "processing_error_code": updated.processing_error_code,
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
    for attr in ('text', 'text_md', 'title', 'language', 'tags', 'summary', 'source', 'byline', 'note'):
        value = request.form.get(attr)
        if value is not None:
            attrs[attr] = value

    session = get_scoped_session()
    service = DocumentService(session)
    try:
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
