"""Model choice for the per-chapter analyses: emotional tone, historical period and dated events.

The three analyses read the text of a chapter and answer with a small JSON, so they share one task in the model
allowlist (``llm_model_registry``) and one household default in ``app_settings`` (key ``chapter_analysis_model``).
The default used to be fixed to Bielik; a reviewer can now see price and context window next to each model and
pick another one per request, or save a different household default.
"""

from library import app_settings

TASK = "chapter_analysis"  # model allowlist of library/llm_model_registry.py
SETTING_KEY = "chapter_analysis_model"  # household default in app_settings
DEFAULT_MODEL = "Bielik-11B-v3.0-Instruct"


def default_model(session) -> str | None:
    """The saved household choice while it is still allowed, else Bielik, else the first available model."""
    from library.llm_model_registry import is_selectable, selectable_models

    saved = app_settings.get_setting(session, SETTING_KEY)
    if isinstance(saved, str) and is_selectable(saved, TASK):
        return saved
    if is_selectable(DEFAULT_MODEL, TASK):
        return DEFAULT_MODEL
    ids = [item["id"] for item in selectable_models(TASK) if item["available"]]
    return ids[0] if ids else None


def has_saved_choice(session) -> bool:
    return isinstance(app_settings.get_setting(session, SETTING_KEY), str)
