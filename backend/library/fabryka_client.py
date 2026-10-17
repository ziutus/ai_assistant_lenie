"""Fabryka AI (fabryka.ai) client for the Basal "calibrated typed decisions" model.

Basal (`basal-1.5-mini`, a 1.5B Bielik-based classifier) does not generate text:
it answers typed questions about a "state" (any JSON value, here a piece of
text) and returns a decision. `POST /v1/systemone` accepts up to 8 named
questions per call, each of type:

- ``choice`` — pick one of the options given in ``criteria``/``levels``,
- ``noul``   — probability of "yes" (e.g. "does the text describe Russian
  army dominance over the Ukrainian one?"),
- ``score``  — a rating on ``levels``.

Spec: https://fabryka.ai/openapi.json (tag "Decisions"). The spec leaves the 200 response
schema empty; observed live (2026-10-17): ``{"model", "answers": {<name>:
{"type": "noul", "noul": 0.976, "probabilities": {"true", "false"},
"confidence"}}, "usage": {...}}``. ``decide()`` returns it raw.

Auth: ``Authorization: Bearer <key>``, config key ``FABRYKA_API_KEY`` (Vault).
Free-tier keys may retain content up to 30 days — do not send private
documents (e.g. contact data, private Obsidian notes) through this client.
"""

import logging

import requests

from library.external_service_events import observed_request

logger = logging.getLogger(__name__)

DECISIONS_URL = "https://fabryka.ai/v1/systemone"
DEFAULT_MODEL = "basal-1.5-mini"
REQUEST_TIMEOUT_S = 60
MAX_QUESTIONS = 8
MAX_INSTRUCTIONS_CHARS = 2000


class FabrykaError(Exception):
    """Base class for Fabryka client failures."""


class FabrykaNotConfigured(FabrykaError):
    """FABRYKA_API_KEY is missing."""


class FabrykaUnexpectedResponse(FabrykaError):
    """The API answered 200 but not in a shape this client understands."""


def _api_key() -> str | None:
    from library.config_loader import load_config
    return load_config().get("FABRYKA_API_KEY")


def decide(state, questions: dict[str, dict], model: str = DEFAULT_MODEL) -> dict:
    """Run one Basal decision call and return the raw JSON response.

    ``questions`` maps a caller-chosen name to a Question object
    (``{"type": "noul", "instructions": "..."}``). Raises ``FabrykaNotConfigured``
    without a key, ``FabrykaError`` for HTTP/transport failures, and
    ``ValueError`` for requests the API would reject with 422 anyway.
    """
    if not questions or len(questions) > MAX_QUESTIONS:
        raise ValueError(f"questions must hold 1..{MAX_QUESTIONS} entries")
    for name, q in questions.items():
        instructions = q.get("instructions") or ""
        if not instructions or len(instructions) > MAX_INSTRUCTIONS_CHARS:
            raise ValueError(f"question {name!r}: instructions must be 1..{MAX_INSTRUCTIONS_CHARS} chars")

    key = _api_key()
    if not key:
        raise FabrykaNotConfigured("FABRYKA_API_KEY not configured")

    try:
        resp = observed_request(
            service="fabryka", operation="systemone",
            request_fn=lambda: requests.post(
                DECISIONS_URL,
                json={"model": model, "state": state, "questions": questions},
                headers={"Authorization": f"Bearer {key}"},
                timeout=REQUEST_TIMEOUT_S,
            ),
        )
        if resp.status_code in (401, 403):
            raise FabrykaError(f"Fabryka rejected the configured key (HTTP {resp.status_code})")
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise FabrykaError(f"Fabryka request failed: {e}") from e
    except ValueError as e:
        raise FabrykaError(f"Fabryka returned invalid JSON: {e}") from e


def yes_probability(text: str, statement: str, model: str = DEFAULT_MODEL) -> float:
    """Probability (0..1) that ``text`` matches ``statement``, via a single ``noul`` question.

    Example: ``yes_probability(article, "Tekst opisuje dominację rosyjskiej armii nad ukraińską.")``.
    The probability is a calibrated model score, not a guarantee — route
    borderline values to a human.
    """
    name = "match"
    result = decide(text, {name: {"type": "noul", "instructions": statement}}, model=model)
    try:
        probability = result["answers"][name]["noul"]
    except (KeyError, TypeError):
        probability = None
    if not isinstance(probability, (int, float)) or isinstance(probability, bool) or not 0.0 <= probability <= 1.0:
        logger.warning("Unrecognised Fabryka response shape: %r", result)
        raise FabrykaUnexpectedResponse("no probability found in Fabryka response")
    return float(probability)
