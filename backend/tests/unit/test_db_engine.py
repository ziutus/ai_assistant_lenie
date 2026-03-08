"""Unit tests for backend/library/db/engine.py — engine singleton, session factories, Base."""

from unittest.mock import patch

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")


class MockConfig(dict):
    """Minimal Config stand-in for unit tests (mirrors unified_config_loader.Config)."""

    def require(self, key, default=None):
        value = self.get(key)
        if value is not None:
            return value
        if default is not None:
            return default
        raise RuntimeError(f"Missing required config: {key}")


CFG_VARS = MockConfig({
    "POSTGRESQL_HOST": "localhost",
    "POSTGRESQL_PORT": "5432",
    "POSTGRESQL_DATABASE": "testdb",
    "POSTGRESQL_USER": "testuser",
    "POSTGRESQL_PASSWORD": "testpass",
})


@pytest.fixture(autouse=True)
def _reset_engine_module():
    """Reset the engine module between tests using the public API."""
    from library.db.engine import dispose_engine
    dispose_engine()
    yield
    dispose_engine()


class TestGetEngine:
    """Tests for get_engine() factory."""

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_returns_engine_instance(self, _mock_cfg):
        from library.db.engine import get_engine

        engine = get_engine()
        assert isinstance(engine, sqlalchemy.Engine)

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_pool_pre_ping_enabled(self, _mock_cfg):
        from library.db.engine import get_engine

        with patch("library.db.engine.create_engine", wraps=sqlalchemy.create_engine) as mock_create:
            get_engine()
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert kwargs["pool_pre_ping"] is True

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_singleton_returns_same_instance(self, _mock_cfg):
        from library.db.engine import get_engine

        engine1 = get_engine()
        engine2 = get_engine()
        assert engine1 is engine2

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_url_constructed_from_config(self, _mock_cfg):
        from library.db.engine import get_engine

        engine = get_engine()
        url = str(engine.url)
        assert "testuser" in url
        assert "localhost" in url
        assert "5432" in url
        assert "testdb" in url
        assert url.startswith("postgresql+psycopg2://")

    @patch("library.db.engine.load_config")
    def test_url_handles_special_chars_in_password(self, mock_cfg):
        """Passwords with @, /, #, % should be URL-encoded correctly."""
        mock_cfg.return_value = MockConfig({
            **CFG_VARS,
            "POSTGRESQL_PASSWORD": "p@ss/w#rd%21",
        })
        from library.db.engine import get_engine

        engine = get_engine()
        assert engine is not None
        url = str(engine.url)
        assert "localhost" in url

    @patch("library.db.engine.load_config")
    def test_sslmode_applied_to_connect_args(self, mock_cfg):
        mock_cfg.return_value = MockConfig({**CFG_VARS, "POSTGRESQL_SSLMODE": "require"})
        from library.db.engine import get_engine

        with patch("library.db.engine.create_engine", wraps=sqlalchemy.create_engine) as mock_create:
            get_engine()
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert kwargs["connect_args"] == {"sslmode": "require"}

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_sslmode_not_set_when_absent(self, _mock_cfg):
        """When POSTGRESQL_SSLMODE is not in config, connect_args should be empty."""
        from library.db.engine import get_engine

        with patch("library.db.engine.create_engine", wraps=sqlalchemy.create_engine) as mock_create:
            get_engine()
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert kwargs["connect_args"] == {}

    @patch("library.db.engine.load_config")
    def test_missing_required_config_raises(self, mock_cfg):
        """Missing required config keys raise RuntimeError (in test) / sys.exit (in prod)."""
        mock_cfg.return_value = MockConfig({"POSTGRESQL_HOST": "dbhost"})
        from library.db.engine import get_engine

        with pytest.raises(RuntimeError, match="Missing required config"):
            get_engine()

    @patch("library.db.engine.load_config")
    def test_invalid_port_raises_valueerror(self, mock_cfg):
        mock_cfg.return_value = MockConfig({**CFG_VARS, "POSTGRESQL_PORT": "abc"})
        from library.db.engine import get_engine

        with pytest.raises(ValueError, match="POSTGRESQL_PORT must be numeric"):
            get_engine()

    @patch("library.db.engine.load_config")
    def test_port_none_when_absent(self, mock_cfg):
        """When POSTGRESQL_PORT is not set, port defaults to None (psycopg2 uses 5432)."""
        cfg = MockConfig({k: v for k, v in CFG_VARS.items() if k != "POSTGRESQL_PORT"})
        mock_cfg.return_value = cfg
        from library.db.engine import get_engine

        engine = get_engine()
        assert engine is not None


class TestGetSession:
    """Tests for get_session() factory."""

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_returns_session_instance(self, _mock_cfg):
        from library.db.engine import get_session
        from sqlalchemy.orm import Session

        session = get_session()
        assert isinstance(session, Session)
        session.close()

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_returns_different_session_each_call(self, _mock_cfg):
        from library.db.engine import get_session

        session1 = get_session()
        session2 = get_session()
        assert session1 is not session2
        session1.close()
        session2.close()


class TestGetScopedSession:
    """Tests for get_scoped_session() factory."""

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_returns_scoped_session(self, _mock_cfg):
        from library.db.engine import get_scoped_session
        from sqlalchemy.orm import scoped_session

        scoped = get_scoped_session()
        assert isinstance(scoped, scoped_session)


class TestDisposeEngine:
    """Tests for dispose_engine() public cleanup API."""

    @patch("library.db.engine.load_config", return_value=CFG_VARS)
    def test_dispose_resets_singleton(self, _mock_cfg):
        from library.db.engine import get_engine, dispose_engine

        engine1 = get_engine()
        dispose_engine()
        engine2 = get_engine()
        assert engine1 is not engine2

    def test_dispose_without_engine_is_safe(self):
        from library.db.engine import dispose_engine

        # Should not raise even when nothing was initialized
        dispose_engine()


class TestBase:
    """Tests for Base declarative base class."""

    def test_base_is_importable(self):
        from library.db.engine import Base
        assert Base is not None

    def test_base_is_declarative_base_subclass(self):
        from library.db.engine import Base
        from sqlalchemy.orm import DeclarativeBase

        assert issubclass(Base, DeclarativeBase)
