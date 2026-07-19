"""Integration tests for FK constraint validation (B-96, Task 10, deferred from B-95/M5).

Requires live database (NAS: 192.168.200.7:5434).
Tests that FK constraints on lookup tables reject invalid values.
"""

import pytest

sa = pytest.importorskip("sqlalchemy")

from sqlalchemy import text as sa_text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

try:
    from library.config_loader import load_config
    load_config()
    from library.db.engine import get_session
    _session = get_session()
    _session.execute(sa_text("SELECT 1"))
    _session.close()
    _db_available = True
except Exception:
    _db_available = False

pytestmark = pytest.mark.integration
skip_no_db = pytest.mark.skipif(not _db_available, reason="No database connection available")


@skip_no_db
class TestDocumentFKConstraints:
    """Test FK constraints on web_documents table."""

    def test_invalid_document_state_raises_integrity_error(self):
        """INSERT with invalid document_state should raise IntegrityError."""
        session = get_session()
        try:
            session.execute(sa_text(
                "INSERT INTO web_documents (url, document_type, document_state) "
                "VALUES ('https://fk-test-invalid-state.example.com', 'link', 'INVALID_STATE')"
            ))
            session.commit()
            pytest.fail("Expected IntegrityError for invalid document_state")
        except IntegrityError:
            session.rollback()
        finally:
            session.close()

    def test_invalid_document_type_raises_integrity_error(self):
        """INSERT with invalid document_type should raise IntegrityError."""
        session = get_session()
        try:
            session.execute(sa_text(
                "INSERT INTO web_documents (url, document_type, document_state) "
                "VALUES ('https://fk-test-invalid-type.example.com', 'INVALID_TYPE', 'URL_ADDED')"
            ))
            session.commit()
            pytest.fail("Expected IntegrityError for invalid document_type")
        except IntegrityError:
            session.rollback()
        finally:
            session.close()

    def test_valid_document_insert_succeeds(self):
        """INSERT with valid FK values should succeed."""
        session = get_session()
        try:
            result = session.execute(sa_text(
                "INSERT INTO web_documents (url, document_type, document_state) "
                "VALUES ('https://fk-test-valid.example.com', 'link', 'URL_ADDED') "
                "RETURNING id"
            ))
            doc_id = result.scalar()
            session.commit()

            # Cleanup
            session.execute(sa_text(
                "DELETE FROM web_documents WHERE id = :id"
            ).bindparams(id=doc_id))
            session.commit()
        finally:
            session.close()


@skip_no_db
class TestSourceFKConstraints:
    """FK on web_documents.source → sources.name (fk_source, ON UPDATE CASCADE)."""

    def test_raw_insert_with_unknown_source_raises_integrity_error(self):
        """Core INSERT bypasses the ORM auto-create hook — FK must reject."""
        session = get_session()
        try:
            session.execute(sa_text(
                "INSERT INTO web_documents (url, document_type, document_state, source) "
                "VALUES ('https://fk-test-src-raw.example.com', 'link', 'URL_ADDED', "
                "'fk-test-no-such-source')"
            ))
            session.commit()
            pytest.fail("Expected IntegrityError for unknown source")
        except IntegrityError:
            session.rollback()
        finally:
            session.close()

    def test_null_source_is_accepted(self):
        session = get_session()
        try:
            result = session.execute(sa_text(
                "INSERT INTO web_documents (url, document_type, document_state, source) "
                "VALUES ('https://fk-test-src-null.example.com', 'link', 'URL_ADDED', NULL) "
                "RETURNING id"
            ))
            doc_id = result.scalar()
            session.commit()

            session.execute(sa_text(
                "DELETE FROM web_documents WHERE id = :id"
            ).bindparams(id=doc_id))
            session.commit()
        finally:
            session.close()

    def test_orm_insert_auto_creates_unknown_source(self):
        """The before_flush hook creates the sources row for ORM write paths."""
        from library.db.models import Source, WebDocument

        name = "fk-test-auto-created-source"
        session = get_session()
        try:
            doc = WebDocument(url="https://fk-test-src-orm.example.com",
                              document_type="link", source=name)
            session.add(doc)
            session.commit()

            created = session.execute(
                sa.select(Source).where(Source.name == name)
            ).scalar_one()
            assert created.is_active is True

            # Two commits: the unit of work does not order cross-table DELETEs
            # by the raw FK here, so the document must go first.
            session.delete(doc)
            session.commit()
            session.delete(created)
            session.commit()
        finally:
            session.rollback()
            session.close()

    def test_rename_cascades_to_documents(self):
        """UPDATE sources.name rewrites web_documents.source (ON UPDATE CASCADE)."""
        old, new = "fk-test-rename-before", "fk-test-rename-after"
        session = get_session()
        try:
            session.execute(sa_text(
                "INSERT INTO sources (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"
            ).bindparams(name=old))
            result = session.execute(sa_text(
                "INSERT INTO web_documents (url, document_type, document_state, source) "
                "VALUES ('https://fk-test-src-rename.example.com', 'link', 'URL_ADDED', :src) "
                "RETURNING id"
            ).bindparams(src=old))
            doc_id = result.scalar()
            session.commit()

            session.execute(sa_text(
                "UPDATE sources SET name = :new WHERE name = :old"
            ).bindparams(new=new, old=old))
            session.commit()

            doc_source = session.execute(sa_text(
                "SELECT source FROM web_documents WHERE id = :id"
            ).bindparams(id=doc_id)).scalar()
            assert doc_source == new

            session.execute(sa_text(
                "DELETE FROM web_documents WHERE id = :id"
            ).bindparams(id=doc_id))
            session.execute(sa_text(
                "DELETE FROM sources WHERE name IN (:new, :old)"
            ).bindparams(new=new, old=old))
            session.commit()
        finally:
            session.rollback()
            session.close()


@skip_no_db
class TestEmbeddingFKConstraints:
    """Test FK constraints on document_embeddings table."""

    def test_invalid_model_raises_integrity_error(self):
        """INSERT embedding with invalid model should raise IntegrityError."""
        session = get_session()
        try:
            # First create a valid document
            result = session.execute(sa_text(
                "INSERT INTO web_documents (url, document_type, document_state) "
                "VALUES ('https://fk-test-emb.example.com', 'link', 'URL_ADDED') "
                "RETURNING id"
            ))
            doc_id = result.scalar()
            session.commit()

            # Try to insert embedding with invalid model
            try:
                session.execute(sa_text(
                    "INSERT INTO document_embeddings (document_id, model, text) "
                    "VALUES (:doc_id, 'nonexistent-model', 'test text')"
                ).bindparams(doc_id=doc_id))
                session.commit()
                pytest.fail("Expected IntegrityError for invalid model")
            except IntegrityError:
                session.rollback()

            # Cleanup
            session.execute(sa_text(
                "DELETE FROM web_documents WHERE id = :id"
            ).bindparams(id=doc_id))
            session.commit()
        finally:
            session.close()
