"""Server-side allowlist of language models a reviewer may pick for a task.

Only models that ``library.ai.ai_ask`` can dispatch are listed; the endpoint rejects any other id, so a
client can never route a document to an arbitrary provider.
"""

# (id, label, provider)
_ORGANIZATION_DESCRIPTION_MODELS: tuple[tuple[str, str, str], ...] = (
    ("Bielik-11B-v3.0-Instruct", "Bielik 11B v3.0 (CloudFerro)", "cloudferro"),
    ("Bielik-11B-v2.3-Instruct", "Bielik 11B v2.3 (CloudFerro)", "cloudferro"),
    ("gpt-4o-mini", "GPT-4o mini (OpenAI)", "openai"),
    ("gemini-2.0-flash-lite-001", "Gemini 2.0 Flash Lite (Google)", "google-vertexai"),
)


def selectable_models(task: str = "organization_description") -> list[dict]:
    """Models offered for ``task`` as ``{id, label, provider}`` dicts."""
    if task != "organization_description":
        return []
    return [{"id": model_id, "label": label, "provider": provider}
            for model_id, label, provider in _ORGANIZATION_DESCRIPTION_MODELS]


def is_selectable(model: str, task: str = "organization_description") -> bool:
    return any(item["id"] == model for item in selectable_models(task))
