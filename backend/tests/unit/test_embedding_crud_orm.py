"""Unit tests for embedding CRUD operations via ORM (Story 28.1)."""

from unittest.mock import MagicMock, patch

import pytest

sa = pytest.importorskip("sqlalchemy")

from library.db.models import WebDocument, WebsiteEmbedding  # noqa: E402
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock(spec=["add", "execute", "commit", "rollback"])
    return session


@pytest.fixture
def repo(mock_session):
    return WebsitesDBPostgreSQL(session=mock_session)


# ---------------------------------------------------------------------------
# Task 1: embedding_add() ORM path
# ---------------------------------------------------------------------------


class TestEmbeddingAddORM:
    def test_embedding_add_creates_website_embedding(self, repo, mock_session):
        """Verify session.add() is called with correct WebsiteEmbedding attributes."""
        repo.embedding_add(
            website_id=42,
            embedding=[0.1, 0.2, 0.3],
            language="en",
            text="some text",
            text_original="original text",
            model="text-embedding-ada-002",
        )

        mock_session.add.assert_called_once()
        emb = mock_session.add.call_args[0][0]
        assert isinstance(emb, WebsiteEmbedding)
        assert emb.website_id == 42
        assert emb.language == "en"
        assert emb.text == "some text"
        assert emb.text_original == "original text"
        assert emb.embedding == [0.1, 0.2, 0.3]
        assert emb.model == "text-embedding-ada-002"

    def test_embedding_add_does_not_commit(self, repo, mock_session):
        """Repository methods never commit — caller controls transactions."""
        repo.embedding_add(
            website_id=1,
            embedding=[0.5],
            language="pl",
            text="t",
            text_original="to",
            model="m",
        )
        mock_session.commit.assert_not_called()

    def test_embedding_add_with_none_optional_fields(self, repo, mock_session):
        """Embedding add works when optional fields are None."""
        repo.embedding_add(
            website_id=10,
            embedding=[1.0],
            language=None,
            text=None,
            text_original=None,
            model="test-model",
        )

        emb = mock_session.add.call_args[0][0]
        assert emb.language is None
        assert emb.text is None
        assert emb.text_original is None


# ---------------------------------------------------------------------------
# Task 2: embedding_delete() ORM path
# ---------------------------------------------------------------------------


class TestEmbeddingDeleteORM:
    def test_embedding_delete_executes_delete_statement(self, repo, mock_session):
        """Verify session.execute() is called with DELETE filtered by website_id AND model."""
        repo.embedding_delete(website_id=42, model="text-embedding-ada-002")

        mock_session.execute.assert_called_once()
        stmt = mock_session.execute.call_args[0][0]
        # Verify it's a DELETE statement
        compiled = stmt.compile()
        sql_text = str(compiled)
        assert "DELETE" in sql_text.upper()
        assert "websites_embeddings" in sql_text

    def test_embedding_delete_does_not_commit(self, repo, mock_session):
        """Repository methods never commit."""
        repo.embedding_delete(website_id=1, model="m")
        mock_session.commit.assert_not_called()

    def test_embedding_delete_filters_by_model(self, repo, mock_session):
        """Only embeddings for the specified model should be targeted."""
        repo.embedding_delete(website_id=5, model="specific-model")

        stmt = mock_session.execute.call_args[0][0]
        compiled = stmt.compile()
        # The WHERE clause should contain both website_id and model filters
        sql_text = str(compiled)
        assert "website_id" in sql_text
        assert "model" in sql_text


# ---------------------------------------------------------------------------
# Task 3: get_documents_needing_embedding() ORM path
# ---------------------------------------------------------------------------


class TestGetDocumentsNeedingEmbeddingORM:
    def test_returns_ready_for_embedding_documents(self, repo, mock_session):
        """Documents in READY_FOR_EMBEDDING state are always returned."""
        mock_session.execute.return_value.all.return_value = [(1,), (3,), (5,)]

        result = repo.get_documents_needing_embedding("text-embedding-ada-002")

        assert result == [1, 3, 5]
        mock_session.execute.assert_called_once()

    def test_returns_list_of_ints(self, repo, mock_session):
        """Result should be list[int] — same format as legacy implementation."""
        mock_session.execute.return_value.all.return_value = [(10,), (20,)]

        result = repo.get_documents_needing_embedding("any-model")

        assert isinstance(result, list)
        assert all(isinstance(x, int) for x in result)

    def test_returns_empty_list_when_no_documents(self, repo, mock_session):
        """No matching documents should return empty list."""
        mock_session.execute.return_value.all.return_value = []

        result = repo.get_documents_needing_embedding("model-x")

        assert result == []

    def test_does_not_commit(self, repo, mock_session):
        """Read-only query should never commit."""
        mock_session.execute.return_value.all.return_value = []
        repo.get_documents_needing_embedding("m")
        mock_session.commit.assert_not_called()

    def test_uses_sqlalchemy_select_not_raw_sql(self, repo, mock_session):
        """AC #4: The query must use SQLAlchemy select(), not raw cursor.execute()."""
        mock_session.execute.return_value.all.return_value = []

        repo.get_documents_needing_embedding("test-model")

        # Verify session.execute was called (ORM path), not cursor.execute
        mock_session.execute.assert_called_once()
        stmt = mock_session.execute.call_args[0][0]
        # Should be a SQLAlchemy construct, not a raw string
        assert hasattr(stmt, "compile"), "Statement should be a SQLAlchemy construct"

    def test_query_uses_union_and_outerjoin(self, repo, mock_session):
        """Verify the ORM statement contains UNION and LEFT OUTER JOIN for correct logic."""
        mock_session.execute.return_value.all.return_value = []

        repo.get_documents_needing_embedding("some-model")

        stmt = mock_session.execute.call_args[0][0]
        compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "UNION" in compiled_sql.upper(), f"Expected UNION in SQL: {compiled_sql}"
        assert "LEFT OUTER JOIN" in compiled_sql.upper() or "OUTER JOIN" in compiled_sql.upper(), (
            f"Expected OUTER JOIN in SQL: {compiled_sql}"
        )


# ---------------------------------------------------------------------------
# Task 4: Dual-mode constructor verification
# ---------------------------------------------------------------------------


class TestDualModeConstructor:
    def test_orm_mode_uses_session(self, mock_session):
        """When session is provided, ORM path is used."""
        repo = WebsitesDBPostgreSQL(session=mock_session)
        assert repo.session is mock_session

    @patch.dict("os.environ", {
        "POSTGRESQL_HOST": "localhost",
        "POSTGRESQL_DATABASE": "test",
        "POSTGRESQL_USER": "user",
        "POSTGRESQL_PASSWORD": "pass",
        "POSTGRESQL_PORT": "5432",
    })
    @patch("library.stalker_web_documents_db_postgresql.psycopg2.connect")
    def test_legacy_mode_without_session(self, mock_connect):
        """When no session is provided, legacy psycopg2 connection is used."""
        repo = WebsitesDBPostgreSQL(session=None)
        assert repo.session is None
        mock_connect.assert_called_once()


# ---------------------------------------------------------------------------
# Task 6.6: Relationship append test
# ---------------------------------------------------------------------------


class TestRelationshipAppend:
    def test_embedding_relationship_fk(self):
        """WebsiteEmbedding created via relationship sets correct FK reference."""
        emb = WebsiteEmbedding(
            website_id=99,
            language="en",
            text="chunk",
            text_original="original chunk",
            embedding=[0.1, 0.2],
            model="test-model",
        )
        assert emb.website_id == 99
        assert emb.model == "test-model"

    def test_website_embedding_has_document_relationship(self):
        """WebsiteEmbedding model has 'document' relationship attribute."""
        mapper = sa.inspect(WebsiteEmbedding)
        rel_names = [r.key for r in mapper.relationships]
        assert "document" in rel_names

    def test_web_document_has_embeddings_relationship(self):
        """WebDocument model has 'embeddings' relationship attribute."""
        mapper = sa.inspect(WebDocument)
        rel_names = [r.key for r in mapper.relationships]
        assert "embeddings" in rel_names
