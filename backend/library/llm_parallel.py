"""Bounded fan-out for independent, I/O-bound LLM calls made while a request is waiting."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import TypeVar

Item = TypeVar("Item")
Result = TypeVar("Result")

# Concurrent calls to one provider; higher values risk rate limits, and a failed batch keeps its entities.
MAX_PARALLEL_LLM_CALLS = 4


def map_llm_calls(call: Callable[[Item], Result], items: Iterable[Item]) -> list[Result]:
    """`[call(item) for item in items]` on a small thread pool, results in input order.

    Every call runs in a copy of the caller's context, so usage rows keep their document, analysis job and
    run (library/llm_usage/context.py). `call` must not touch the caller's database session or any other
    shared mutable state. The first exception, in input order, propagates once all calls have finished.
    """
    items = list(items)
    if len(items) <= 1:
        return [call(item) for item in items]
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_LLM_CALLS, thread_name_prefix="llm") as pool:
        futures = [pool.submit(copy_context().run, call, item) for item in items]
    return [future.result() for future in futures]
