"""Server-side allowlist of language models a reviewer may pick for a task.

Only models that ``library.ai.ai_ask`` can dispatch are listed; the endpoint rejects any other id, so a
client can never route a document to an arbitrary provider. OpenRouter models are listed only while the
``OPENROUTER_ENABLED`` flag is on, because they send the document text to an external intermediary.
"""

# (id, label, provider, external, verified) — ``verified`` False = id/price/quality not yet checked by a human.
_ORGANIZATION_DESCRIPTION_MODELS: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("Bielik-11B-v3.0-Instruct", "Bielik 11B v3.0 (CloudFerro)", "cloudferro", False, True),
    ("Bielik-11B-v2.3-Instruct", "Bielik 11B v2.3 (CloudFerro)", "cloudferro", False, True),
    ("gpt-4o-mini", "GPT-4o mini (OpenAI)", "openai", False, True),
    ("gemini-2.0-flash-lite-001", "Gemini 2.0 Flash Lite (Google)", "google-vertexai", False, True),
    ("openrouter/openai/gpt-4o-mini", "GPT-4o mini (OpenRouter)", "openrouter", True, False),
    ("openrouter/google/gemini-2.0-flash-lite-001", "Gemini 2.0 Flash Lite (OpenRouter)", "openrouter", True, False),
    ("openrouter/meta-llama/llama-3.1-8b-instruct", "Llama 3.1 8B (OpenRouter)", "openrouter", True, False),
    ("openrouter/qwen/qwen-2.5-7b-instruct", "Qwen 2.5 7B (OpenRouter)", "openrouter", True, False),
)


def _openrouter_enabled() -> bool:
    from library.api.openrouter.openrouter_completion import is_enabled

    try:
        return is_enabled()
    except Exception:  # config unavailable -> treat the external provider as off
        return False


def selectable_models(task: str = "organization_description") -> list[dict]:
    """Models offered for ``task`` as ``{id, label, provider, external, verified}`` dicts."""
    if task != "organization_description":
        return []
    show_openrouter = _openrouter_enabled()
    return [{"id": model_id, "label": label, "provider": provider, "external": external, "verified": verified}
            for model_id, label, provider, external, verified in _ORGANIZATION_DESCRIPTION_MODELS
            if provider != "openrouter" or show_openrouter]


def is_selectable(model: str, task: str = "organization_description") -> bool:
    return any(item["id"] == model for item in selectable_models(task))
