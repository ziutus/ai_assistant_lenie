"""Remove obsolete translation processing states and error codes.

The application embeds source-language text directly.  The translation endpoint
and translated document columns no longer exist, so keeping workflow values for
that removed pipeline only allows documents to get stuck in unreachable states.

Revision ID: d18f4a6b2c7e
Revises: c07c2d94a19f
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d18f4a6b2c7e"
down_revision: Union[str, None] = "c07c2d94a19f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRANSLATION_ERRORS = (
    "TITLE_TRANSLATION_ERROR",
    "TEXT_TRANSLATION_ERROR",
    "SUMMARY_TRANSLATION_ERROR",
    "MISSING_TRANSLATION",
    "TRANSLATION_ERROR",
)


def upgrade() -> None:
    quoted_errors = ", ".join(f"'{value}'" for value in _TRANSLATION_ERRORS)

    # A document whose only terminal failure was the removed translation step
    # needs a human decision about its source content; it must not remain in
    # ERROR with an error code that no longer exists.
    op.execute(
        f"""
        UPDATE documents
        SET processing_status = 'NEED_MANUAL_REVIEW', processing_error_code = 'NONE'
        WHERE processing_status = 'ERROR'
          AND processing_error_code IN ({quoted_errors})
        """
    )
    op.execute(
        f"""
        UPDATE documents
        SET processing_error_code = 'NONE'
        WHERE processing_error_code IN ({quoted_errors})
        """
    )

    # No translation stage remains.  Historical queued rows can proceed using
    # the configured multilingual embedding model.
    op.execute(
        """
        UPDATE documents
        SET processing_status = 'READY_FOR_EMBEDDING'
        WHERE processing_status = 'READY_FOR_TRANSLATION'
        """
    )

    op.execute(
        f"DELETE FROM processing_error_types WHERE name IN ({quoted_errors})"
    )
    op.execute(
        "DELETE FROM processing_status_types WHERE name = 'READY_FOR_TRANSLATION'"
    )


def downgrade() -> None:
    # Normalized document rows cannot be assigned their historical error code
    # losslessly.  Downgrade restores only the accepted lookup values.
    op.execute(
        """
        INSERT INTO processing_status_types (name)
        VALUES ('READY_FOR_TRANSLATION')
        ON CONFLICT (name) DO NOTHING
        """
    )
    values = ", ".join(f"('{value}')" for value in _TRANSLATION_ERRORS)
    op.execute(
        f"""
        INSERT INTO processing_error_types (name)
        VALUES {values}
        ON CONFLICT (name) DO NOTHING
        """
    )
