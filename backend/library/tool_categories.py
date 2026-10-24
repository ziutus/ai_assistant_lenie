"""One spelling per radar category.

Catalog imports bring their own headings (``security`` vs ``Security``, ``decision-models`` vs
``DecisionModels``), which split one category into several dropdown entries. Writers pass the value
through :func:`canonical_category`; spellings it does not know are kept as typed.
"""

# Keyed by the folded form (lowercase letters and digits only), so "decision-models", "Decision Models"
# and "DecisionModels" are all the same key.
CANONICAL_CATEGORIES: dict[str, str] = {
    "security": "Security",
    "decisionmodels": "DecisionModels",
    "cloud": "Cloud",
    "database": "Database",
    "scraping": "Scraping",
    "workflow": "Workflow",
    "frontendtooling": "FrontendTooling",
    "pythontooling": "PythonTooling",
    "infrastructureascode": "InfrastructureAsCode",
    "infrastructure": "InfraManagement",
    "inframanagement": "InfraManagement",
    "notes": "Notatki i produktywność",
}


def fold_category(value: str | None) -> str:
    """Fold spellings such as ``DecisionModels`` and ``decision-models`` into one key."""
    return "".join(char for char in (value or "").lower() if char.isalnum())


def canonical_category(value: str | None) -> str | None:
    """The canonical spelling of ``value``; unknown categories and empty values are returned stripped."""
    text = (value or "").strip()
    if not text:
        return None
    return CANONICAL_CATEGORIES.get(fold_category(text), text)
