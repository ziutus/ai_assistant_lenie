"""Request-independent context attached to LLM usage rows."""

from contextlib import contextmanager
from contextvars import ContextVar

_document_id: ContextVar[int | None] = ContextVar("llm_document_id", default=None)
_analysis_job_id: ContextVar[str | None] = ContextVar("llm_analysis_job_id", default=None)
_analysis_run_id: ContextVar[int | None] = ContextVar("llm_analysis_run_id", default=None)


def current_usage_context() -> tuple[int | None, str | None, int | None]:
    return _document_id.get(), _analysis_job_id.get(), _analysis_run_id.get()


@contextmanager
def llm_usage_context(*, document_id: int | None = None, analysis_job_id: str | None = None,
                      analysis_run_id: int | None = None):
    document_token = _document_id.set(document_id)
    job_token = _analysis_job_id.set(analysis_job_id)
    run_token = _analysis_run_id.set(analysis_run_id)
    try:
        yield
    finally:
        _analysis_run_id.reset(run_token)
        _analysis_job_id.reset(job_token)
        _document_id.reset(document_token)
