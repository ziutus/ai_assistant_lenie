"""Narrative detection: score a text against a documented set of narratives.

Each narrative becomes one Basal ``noul`` question ("does the text present or
repeat this thesis?"); questions go to Fabryka in batches of
``fabryka_client.MAX_QUESTIONS``. The score is topical match, not intent: a
report that *describes* a narrative scores high as well, so the result is a
signal for human review, never a verdict. See ``imports/narrative_trial.py``.
"""

import json
import logging
from dataclasses import dataclass

from library import fabryka_client

logger = logging.getLogger(__name__)

PIECE_MAX_CHARS = 1800
# Fabryka rejects a request (state + questions) above 6000 bytes with 422; keep headroom for the envelope.
REQUEST_BUDGET_BYTES = 5600
FIRST_SENTENCE_MAX_CHARS = 260
INSTRUCTIONS_MAX_CHARS = fabryka_client.MAX_INSTRUCTIONS_CHARS


@dataclass(frozen=True)
class NarrativeDef:
    code: str
    title: str
    description: str


def load_seed(path: str) -> tuple[dict, list[NarrativeDef]]:
    """Read a narrative set seed file (``data/narratives/*.json``)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["set"], [NarrativeDef(**n) for n in data["narratives"]]


def question_instructions(narrative: NarrativeDef) -> str:
    """The yes/no statement sent to the classifier: title plus the description's first sentence.

    Full descriptions (400-1500 chars each) do not fit 24 questions into Fabryka's 6000-byte
    request limit next to the text, so only the lead sentence is kept.
    """
    first = narrative.description.split(". ")[0].strip()[:FIRST_SENTENCE_MAX_CHARS]
    text = f"Tekst przedstawia lub powtarza narrację: „{narrative.title}”. {first}"
    return text[:INSTRUCTIONS_MAX_CHARS]


def _request_bytes(piece: str, questions: dict) -> int:
    return len(json.dumps({"model": fabryka_client.DEFAULT_MODEL, "state": piece, "questions": questions},
                          ensure_ascii=False).encode("utf-8"))


def batch_narratives(piece: str, narratives: list[NarrativeDef]) -> list[list[NarrativeDef]]:
    """Greedy batches of at most MAX_QUESTIONS narratives whose request stays within the byte budget."""
    batches: list[list[NarrativeDef]] = []
    current: list[NarrativeDef] = []
    for n in narratives:
        trial = {x.code: {"type": "noul", "instructions": question_instructions(x)} for x in [*current, n]}
        if current and (len(current) >= fabryka_client.MAX_QUESTIONS or _request_bytes(piece, trial) > REQUEST_BUDGET_BYTES):
            batches.append(current)
            current = []
        current.append(n)
    if current:
        batches.append(current)
    return batches


def split_pieces(text: str, max_chars: int = PIECE_MAX_CHARS) -> list[str]:
    """Split on paragraph boundaries into pieces of at most ``max_chars`` (a longer paragraph is cut)."""
    pieces: list[str] = []
    current = ""
    for para in (text or "").split("\n"):
        para = para.strip()
        if not para:
            continue
        while len(para) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(para[:max_chars])
            para = para[max_chars:]
        if current and len(current) + len(para) + 1 > max_chars:
            pieces.append(current)
            current = ""
        current = f"{current}\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def score_piece(piece: str, narratives: list[NarrativeDef], model: str = fabryka_client.DEFAULT_MODEL) -> dict[str, dict]:
    """Score one text piece against all narratives; returns ``{code: {"probability", "confidence"}}``."""
    scores: dict[str, dict] = {}
    for batch in batch_narratives(piece, narratives):
        questions = {n.code: {"type": "noul", "instructions": question_instructions(n)} for n in batch}
        answers = fabryka_client.decide(piece, questions, model=model).get("answers") or {}
        for n in batch:
            answer = answers.get(n.code) or {}
            probability = answer.get("noul")
            if not isinstance(probability, (int, float)) or isinstance(probability, bool) or not 0.0 <= probability <= 1.0:
                raise fabryka_client.FabrykaUnexpectedResponse(f"no probability for {n.code}: {answer!r}")
            scores[n.code] = {"probability": float(probability), "confidence": answer.get("confidence")}
    return scores


def score_text(text: str, narratives: list[NarrativeDef], max_pieces: int = 4,
               model: str = fabryka_client.DEFAULT_MODEL) -> dict[str, dict]:
    """Score a document: each narrative keeps its best-matching piece (``piece`` = 0-based index)."""
    best: dict[str, dict] = {}
    for index, piece in enumerate(split_pieces(text)[:max_pieces]):
        for code, result in score_piece(piece, narratives, model=model).items():
            if code not in best or result["probability"] > best[code]["probability"]:
                best[code] = {**result, "piece": index}
    return best
