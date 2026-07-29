from unittest.mock import MagicMock

import pytest

from library.job_queue import JOB_TYPES, claim


def test_document_and_legacy_job_types_are_supported():
    assert {"document_prepare", "legacy_aws_pull"} <= JOB_TYPES


def test_claim_requires_non_empty_allowed_types():
    with pytest.raises(ValueError, match="must not be empty"):
        claim(MagicMock(), set())


def test_claim_rejects_unknown_allowed_type():
    with pytest.raises(ValueError, match="unsupported job types"):
        claim(MagicMock(), {"not_a_job"})
