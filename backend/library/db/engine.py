"""SQLAlchemy engine singleton, DeclarativeBase, and session factories.

Provides:
- ``Base`` — DeclarativeBase for ORM models (Story 26.2)
- ``get_engine()`` — singleton Engine built from config_loader (Vault/env/AWS SSM)
- ``get_session()`` — plain Session for scripts (caller manages lifecycle)
- ``get_scoped_session()`` — thread-local scoped_session for Flask requests
- ``dispose_engine()`` — tear down engine and reset all singletons
"""

import threading

from sqlalchemy import create_engine, Engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    scoped_session,
    sessionmaker,
)

from library.config_loader import load_config

# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Module-level singletons (lazy-initialized, guarded by _lock)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_engine: Engine | None = None
_session_factory: sessionmaker | None = None
_scoped_session_factory: scoped_session | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_engine() -> Engine:
    """Return the singleton SQLAlchemy engine.

    Reads connection parameters via ``load_config()`` (supports Vault, env,
    AWS SSM backends). Required keys: ``POSTGRESQL_HOST``,
    ``POSTGRESQL_DATABASE``, ``POSTGRESQL_USER``, ``POSTGRESQL_PASSWORD``.

    Optional: ``POSTGRESQL_PORT`` (default 5432), ``POSTGRESQL_SSLMODE``.

    Exits the process if required config keys are missing
    (via ``Config.require()`` convention — logs error and calls ``sys.exit(1)``).
    """
    global _engine
    if _engine is not None:
        return _engine

    with _lock:
        if _engine is not None:
            return _engine

        cfg = load_config()

        host = cfg.require("POSTGRESQL_HOST")
        database = cfg.require("POSTGRESQL_DATABASE")
        user = cfg.require("POSTGRESQL_USER")
        password = cfg.require("POSTGRESQL_PASSWORD")

        port_raw = cfg.get("POSTGRESQL_PORT")
        if port_raw is not None:
            try:
                port = int(port_raw)
            except (ValueError, TypeError):
                raise ValueError(f"POSTGRESQL_PORT must be numeric, got: {port_raw!r}")
        else:
            port = None

        url = URL.create(
            drivername="postgresql+psycopg2",
            username=user,
            password=password,
            host=host,
            port=port,
            database=database,
        )

        connect_args: dict[str, str] = {}
        sslmode = cfg.get("POSTGRESQL_SSLMODE")
        if sslmode:
            connect_args["sslmode"] = sslmode

        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        return _engine


def get_session() -> Session:
    """Return a new plain Session bound to the engine.

    For use in scripts and batch processing. The caller is responsible
    for closing the session (``session.close()``).
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory()


def get_scoped_session() -> scoped_session:
    """Return the thread-local scoped_session factory.

    For use in Flask request handling. Call ``scoped_session.remove()``
    in ``@app.teardown_appcontext`` to clean up (wired in Story 26.3).
    """
    global _scoped_session_factory
    if _scoped_session_factory is None:
        _scoped_session_factory = scoped_session(sessionmaker(bind=get_engine()))
    return _scoped_session_factory


def dispose_engine() -> None:
    """Dispose the engine and reset all singletons.

    Call on application shutdown or in tests to release the connection pool.
    """
    global _engine, _session_factory, _scoped_session_factory
    with _lock:
        if _scoped_session_factory is not None:
            _scoped_session_factory.remove()
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None
        _scoped_session_factory = None
