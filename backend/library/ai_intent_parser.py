"""LLM-based intent parser for natural language command recognition.

Sends a system prompt defining available commands and expected JSON output,
then the user's natural language text. Returns a structured ParsedIntent
with command, args, and confidence score.
"""

import json
import logging

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.5

SYSTEM_PROMPT = """You are a command classifier for a knowledge base assistant.
Given a user message, determine which command the user wants to execute.

Available commands:
- version: Show system version (no args). Examples: "what version?", "which version is running?"
- count: Show document count (no args). Examples: "how many articles?", "ile mam dokumentów?"
- check: Check if URL exists in database (args: {url: str}). Examples: "do I have this? https://...", "czy mam ten link?"
- add: Save a URL to knowledge base (args: {url: str, type?: str}). Examples: "save https://...", "dodaj ten artykuł"
- info: Get document details by numeric ID (args: {id: int}). Examples: "show document 42", "pokaż dokument 15"
- search: Search for documents by query (args: {query: str}). Examples: "find articles about Kubernetes", "szukaj artykułów o AI"
- unknown: Cannot determine intent or message is unrelated.

Valid document types for 'add': webpage, link, youtube, movie, text_message, text.

Respond ONLY with valid JSON (no markdown, no explanation):
{"command": "<command_name>", "args": {<args if any>}, "confidence": <0.0-1.0>}

Rules:
- Extract URLs from the message when relevant (for check/add commands)
- Extract numeric IDs for info command
- Set confidence to 0.0-1.0 based on how certain you are
- If the message is ambiguous or unrelated, use command "unknown" with confidence 0.0
- Always respond with valid JSON, nothing else"""


def parse_intent(text: str, model: str | None = None) -> dict:
    """Parse user text into a structured command intent using LLM.

    Args:
        text: Natural language user message.
        model: LLM model to use. If None, reads from config INTENT_PARSER_MODEL.

    Returns:
        Dict with keys: command (str), args (dict), confidence (float).
        On failure returns {"command": "unknown", "args": {}, "confidence": 0.0}.
    """
    if not text or not text.strip():
        return {"command": "unknown", "args": {}, "confidence": 0.0}

    if model is None:
        from library.config_loader import load_config
        cfg = load_config()
        model = cfg.get("INTENT_PARSER_MODEL", "Bielik-11B-v3.0-Instruct")

    # NOTE: ai_ask() accepts a single string, so system prompt and user text
    # are concatenated. Ideally these should be separate system/user messages
    # for stronger prompt injection defense. Response validation below mitigates this.
    sanitized_text = text.strip()[:2000]  # Limit input length to prevent abuse
    prompt = f"{SYSTEM_PROMPT}\n\nUser message: {sanitized_text}"

    try:
        from library.ai import ai_ask
        ai_response = ai_ask(prompt, model=model, temperature=0.1, max_token_count=256)
        raw_response = ai_response.response_text
        if not raw_response:
            logger.warning("Empty LLM response for intent parsing")
            return {"command": "unknown", "args": {}, "confidence": 0.0}

        result = _parse_llm_response(raw_response)
        logger.debug("Intent parsed: command=%s, confidence=%.2f", result["command"], result["confidence"])
        return result

    except Exception:
        logger.exception("LLM intent parsing failed")
        return {"command": "unknown", "args": {}, "confidence": 0.0}


def _parse_llm_response(raw: str) -> dict:
    """Parse and validate LLM JSON response.

    Handles markdown code blocks, extra whitespace, and malformed JSON.
    Validates command is in the allowed set and confidence is a valid float.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Malformed LLM JSON response: %s", cleaned[:200])
        return {"command": "unknown", "args": {}, "confidence": 0.0}

    if not isinstance(data, dict):
        return {"command": "unknown", "args": {}, "confidence": 0.0}

    allowed_commands = {"version", "count", "check", "add", "info", "search", "unknown"}
    command = data.get("command", "unknown")
    if command not in allowed_commands:
        command = "unknown"

    args = data.get("args", {})
    if not isinstance(args, dict):
        args = {}

    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.0

    if confidence < CONFIDENCE_THRESHOLD:
        command = "unknown"

    return {"command": command, "args": args, "confidence": confidence}
