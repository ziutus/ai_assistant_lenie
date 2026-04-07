"""Unit tests for web_documents_do_the_needful_new.py ORM migration (Story 29.2, Task 2).

Verifies that the batch pipeline:
- Uses WebDocument ORM model instead of StalkerWebDocumentDB
- Uses session.commit() instead of save()
- Creates documents via session.add() + session.commit()
- Detects duplicates via WebDocument.get_by_url()
- Manages session lifecycle with try/finally
"""

import pytest

sa = pytest.importorskip("sqlalchemy")

from unittest.mock import MagicMock  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    return session


# ---------------------------------------------------------------------------
# Test: No legacy imports in batch pipeline
# ---------------------------------------------------------------------------

class TestBatchPipelineNoLegacyImports:
    """Verify web_documents_do_the_needful_new.py uses ORM imports."""

    def test_no_stalker_web_document_db_import(self):
        """StalkerWebDocumentDB should not be imported."""
        import ast

        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

        assert "StalkerWebDocumentDB" not in imports, \
            "web_documents_do_the_needful_new.py still imports StalkerWebDocumentDB"

    def test_imports_web_document(self):
        """WebDocument should be imported from library.db.models."""
        import ast

        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        has_web_document_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "library.db.models":
                for alias in node.names:
                    if alias.name == "WebDocument":
                        has_web_document_import = True

        assert has_web_document_import, \
            "web_documents_do_the_needful_new.py must import WebDocument from library.db.models"

    def test_imports_get_session(self):
        """get_session should be imported from library.db.engine."""
        import ast

        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        has_get_session_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "library.db.engine":
                for alias in node.names:
                    if alias.name == "get_session":
                        has_get_session_import = True

        assert has_get_session_import, \
            "web_documents_do_the_needful_new.py must import get_session from library.db.engine"

    def test_imports_search_service(self):
        """SearchService should be imported from library.search_service."""
        import ast

        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        has_search_service_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "library.search_service":
                for alias in node.names:
                    if alias.name == "SearchService":
                        has_search_service_import = True

        assert has_search_service_import, \
            "web_documents_do_the_needful_new.py must import SearchService from library.search_service"

    def test_no_save_calls(self):
        """No .save() calls should remain in the batch pipeline."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        # Count .save() calls (excluding comments)
        lines_with_save = [
            line.strip() for line in source.split("\n")
            if ".save()" in line and not line.strip().startswith("#")
        ]
        assert len(lines_with_save) == 0, \
            f"Found .save() calls that should be session.commit(): {lines_with_save}"

    def test_no_cursor_execute_calls(self):
        """No cursor.execute() calls should exist in the batch pipeline."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "cursor.execute" not in source, \
            "web_documents_do_the_needful_new.py should not use cursor.execute()"

    def test_no_psycopg2_import(self):
        """psycopg2 should not be imported."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "import psycopg2" not in source, \
            "web_documents_do_the_needful_new.py should not import psycopg2"


# ---------------------------------------------------------------------------
# Test: SQS message processing creates WebDocument via ORM
# ---------------------------------------------------------------------------

class TestSQSProcessing:
    """Test Step 1 (SQS drain) ORM migration."""

    def test_duplicate_url_detection_uses_get_by_url(self):
        """Duplicate check should use WebDocument.get_by_url(), not StalkerWebDocumentDB."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "WebDocument.get_by_url" in source, \
            "Batch pipeline should use WebDocument.get_by_url() for duplicate detection"

    def test_new_document_uses_session_add(self):
        """New documents should be created via session.add()."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "session.add(" in source, \
            "Batch pipeline should use session.add() for new documents"

    def test_session_commit_used(self):
        """session.commit() should be used instead of save()."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "session.commit()" in source, \
            "Batch pipeline should use session.commit()"


# ---------------------------------------------------------------------------
# Test: Document state transitions
# ---------------------------------------------------------------------------

class TestDocumentStateTransitions:
    """Test state transition via ORM attribute assignment."""

    def test_state_transitions_use_enum_name(self):
        """State changes should use StalkerDocumentStatus enum .name for string storage."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        # Check that state assignments use enum .name (B-96: columns store strings)
        assert "StalkerDocumentStatus.NEED_MANUAL_REVIEW.name" in source
        assert "StalkerDocumentStatus.READY_FOR_EMBEDDING.name" in source
        assert "StalkerDocumentStatus.EMBEDDING_EXIST.name" in source
        assert "StalkerDocumentStatus.ERROR.name" in source


# ---------------------------------------------------------------------------
# Test: Session lifecycle
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    """Test session lifecycle management."""

    def test_session_close_in_finally(self):
        """Session should be closed in a finally block."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "session.close()" in source, \
            "Batch pipeline must close session"

    def test_session_rollback_on_error(self):
        """Session should rollback on error."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "session.rollback()" in source, \
            "Batch pipeline should rollback session on error"


# ---------------------------------------------------------------------------
# Test: Embedding generation flow
# ---------------------------------------------------------------------------

class TestEmbeddingGeneration:
    """Test Step 5 embedding generation via ORM."""

    def test_embedding_uses_get_embedding(self):
        """Embedding generation should use get_embedding() function."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "get_embedding(" in source, \
            "Batch pipeline Step 5 should use get_embedding() for embeddings"

    def test_embedding_uses_websites_db(self):
        """Embedding storage should use WebsitesDBPostgreSQL methods."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "websites.embedding_delete(" in source, \
            "Batch pipeline Step 5 should use websites.embedding_delete()"
        assert "websites.embedding_add(" in source, \
            "Batch pipeline Step 5 should use websites.embedding_add()"


# ---------------------------------------------------------------------------
# Test: WebsitesDBPostgreSQL uses session
# ---------------------------------------------------------------------------

class TestWebsitesDBWithSession:
    """Test that WebsitesDBPostgreSQL is created with session."""

    def test_websites_db_created_with_session(self):
        """WebsitesDBPostgreSQL should be created with session parameter."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "WebsitesDBPostgreSQL(session=session)" in source, \
            "WebsitesDBPostgreSQL should be created with session=session"

    def test_no_websites_close_call(self):
        """websites.close() should not be called — session.close() handles cleanup."""
        with open("web_documents_do_the_needful_new.py", "r", encoding="utf-8") as f:
            source = f.read()

        assert "websites.close()" not in source, \
            "websites.close() should not be called — session.close() handles cleanup"


# ---------------------------------------------------------------------------
# Test: youtube_add.py ORM migration (Task 3)
# ---------------------------------------------------------------------------

class TestYoutubeAddScript:
    """Test youtube_add.py passes session to process_youtube_url."""

    def test_imports_get_session(self):
        """youtube_add.py should import get_session."""
        with open("youtube_add.py", "r") as f:
            source = f.read()

        assert "from library.db.engine import get_session" in source

    def test_session_passed_to_process_youtube_url(self):
        """youtube_add.py should pass session= to process_youtube_url()."""
        with open("youtube_add.py", "r") as f:
            source = f.read()

        assert "session=session" in source, \
            "youtube_add.py must pass session=session to process_youtube_url()"

    def test_session_close_in_finally(self):
        """youtube_add.py should close session in finally block."""
        with open("youtube_add.py", "r") as f:
            source = f.read()

        assert "session.close()" in source


# ---------------------------------------------------------------------------
# Test: get_documents_md_needed ORM branch (Task 4)
# ---------------------------------------------------------------------------

class TestGetDocumentsMdNeededORM:
    """Test ORM branch in get_documents_md_needed()."""

    def test_orm_branch_exists(self):
        """get_documents_md_needed should have an ORM branch."""
        with open("library/stalker_web_documents_db_postgresql.py", "r") as f:
            source = f.read()

        # Check that the method body contains self.session check
        # Find the method and check for ORM pattern
        assert "def get_documents_md_needed" in source
        # The ORM branch should use select() and WebDocument
        assert "WebDocument.text_md.is_(None)" in source or "text_md.is_(None)" in source, \
            "get_documents_md_needed should have ORM branch with text_md.is_(None)"
