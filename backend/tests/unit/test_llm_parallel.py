import threading

import pytest

from library.llm_parallel import MAX_PARALLEL_LLM_CALLS, map_llm_calls
from library.llm_usage.context import current_usage_context, llm_usage_context


def test_calls_overlap_and_results_keep_input_order():
    # Every worker waits for the others: a sequential implementation breaks the barrier.
    barrier = threading.Barrier(MAX_PARALLEL_LLM_CALLS, timeout=5)

    def call(item):
        barrier.wait()
        return item * 10

    items = list(range(MAX_PARALLEL_LLM_CALLS * 2))
    assert map_llm_calls(call, items) == [item * 10 for item in items]


def test_usage_context_reaches_worker_threads():
    with llm_usage_context(document_id=11287, analysis_job_id="job", analysis_run_id=7):
        assert map_llm_calls(lambda _: current_usage_context(), range(6)) == [(11287, "job", 7)] * 6
    assert current_usage_context() == (None, None, None)


def test_exception_propagates_and_empty_input_is_fine():
    def call(item):
        if item == 2:
            raise ValueError("boom")
        return item

    with pytest.raises(ValueError, match="boom"):
        map_llm_calls(call, range(5))
    assert map_llm_calls(call, []) == []
