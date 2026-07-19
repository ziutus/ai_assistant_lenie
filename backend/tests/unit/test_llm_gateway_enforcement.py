"""Architectural guard: business code must not bypass auditable LLM calls."""

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
ALLOWED = {
    Path("library/ai.py"),
    Path("library/api/arklabs/arklabs_completion.py"),
    Path("library/api/cloudferro/sherlock/sherlock.py"),
}
LOW_LEVEL_FUNCTIONS = {"arklabs_get_completion", "sherlock_get_completion"}


def test_business_code_does_not_call_low_level_llm_clients():
    violations = []
    paths = [*BACKEND.joinpath("library").rglob("*.py"), *BACKEND.joinpath("imports").rglob("*.py")]
    paths += list(BACKEND.glob("*.py"))
    for path in paths:
        relative = path.relative_to(BACKEND)
        if relative in ALLOWED or "tests" in relative.parts or "test_code" in relative.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in LOW_LEVEL_FUNCTIONS:
                    violations.append(f"{relative}:{node.lineno} calls {node.func.id}")
    assert violations == [], "LLM calls bypass central ai_ask audit:\n" + "\n".join(violations)


def test_business_ai_calls_name_their_operational_moment():
    violations = []
    for path in BACKEND.joinpath("library").rglob("*.py"):
        relative = path.relative_to(BACKEND)
        if relative == Path("library/ai.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ai_ask":
                if not any(keyword.arg == "operation" for keyword in node.keywords):
                    violations.append(f"{relative}:{node.lineno} has no operation")
    assert violations == [], "Audited LLM calls without an operational moment:\n" + "\n".join(violations)
