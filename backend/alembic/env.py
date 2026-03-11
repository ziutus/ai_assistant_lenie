import sys
import os
from logging.config import fileConfig

from alembic import context

# Ensure backend/ is on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load config (Vault/AWS/env) so POSTGRESQL_* vars are in os.environ
from library.config_loader import load_config  # noqa: E402
load_config()

from library.db.engine import get_engine, Base  # noqa: E402

# CRITICAL: Import models to register them on Base.metadata
import library.db.models  # noqa: E402, F401

target_metadata = Base.metadata

# Alembic Config object — provides access to .ini file values
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def include_object(object, name, type_, reflected, compare_to):
    """Exclude indexes and known-drift columns from autogenerate."""
    if type_ == "index":
        return False
    # Exclude lookup tables created by B-94 (raw SQL migration) until B-96 adds ORM models.
    # Without this filter, autogenerate would suggest DROP TABLE for these tables.
    _LOOKUP_TABLES = {"document_status_types", "document_status_error_types", "document_types", "embedding_models"}
    if type_ == "table" and name in _LOOKUP_TABLES:
        return False
    # Ignore document_state_error type drift (DDL: TEXT, ORM: SAEnum with native_enum=False)
    # VARCHAR without length and TEXT are equivalent in PostgreSQL — no real schema change needed.
    # TODO: Remove this exclusion after standardizing the column type (Epic 29 cleanup).
    if (
        type_ == "column"
        and name == "document_state_error"
        and hasattr(object, "table")
        and object.table is not None
        and object.table.name == "web_documents"
    ):
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without DB connection)."""
    url = str(get_engine().url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to database)."""
    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
