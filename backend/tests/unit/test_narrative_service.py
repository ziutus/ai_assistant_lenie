"""Tests for library.narrative_service (Fabryka calls are mocked)."""

from unittest.mock import patch

import pytest

from library import narrative_service as ns
from library.narrative_service import NarrativeDef


def _narratives(count=24, desc_len=600):
    return [
        NarrativeDef(code=f"RU-{i:02d}", title=f"Teza numer {i}", description=("To jest opis tezy. " + "x" * desc_len))
        for i in range(1, count + 1)
    ]


def test_question_instructions_keeps_title_and_first_sentence_only():
    text = ns.question_instructions(NarrativeDef("A-01", "Teza", "Pierwsze zdanie. Drugie zdanie bardzo długie."))
    assert "„Teza”" in text
    assert "Pierwsze zdanie" in text
    assert "Drugie" not in text


def test_split_pieces_respects_max_chars():
    text = "\n".join(["a" * 700] * 10)
    pieces = ns.split_pieces(text, max_chars=1800)
    assert all(len(p) <= 1800 for p in pieces)
    assert "".join(pieces).replace("\n", "") == "a" * 7000


def test_split_pieces_cuts_overlong_paragraph():
    pieces = ns.split_pieces("b" * 4000, max_chars=1800)
    assert [len(p) for p in pieces] == [1800, 1800, 400]


@pytest.mark.parametrize("piece_chars", [200, 1800])
def test_batches_stay_within_request_budget_and_question_cap(piece_chars):
    piece = "ą" * piece_chars  # 2 bytes per char in UTF-8
    narratives = _narratives()
    batches = ns.batch_narratives(piece, narratives)
    assert [n.code for b in batches for n in b] == [n.code for n in narratives]
    for batch in batches:
        assert len(batch) <= ns.fabryka_client.MAX_QUESTIONS
        questions = {n.code: {"type": "noul", "instructions": ns.question_instructions(n)} for n in batch}
        assert len(batch) == 1 or ns._request_bytes(piece, questions) <= ns.REQUEST_BUDGET_BYTES


def test_score_text_keeps_best_piece_per_narrative():
    narratives = _narratives(count=2)
    text = "\n".join(["a" * 1500, "b" * 1500])  # two pieces

    def fake_decide(piece, questions, model=None):
        high = 0.9 if piece.startswith("b") else 0.2
        return {"answers": {code: {"noul": high, "confidence": high} for code in questions}}

    with patch.object(ns.fabryka_client, "decide", side_effect=fake_decide):
        scores = ns.score_text(text, narratives, max_pieces=4)

    assert scores["RU-01"] == {"probability": 0.9, "confidence": 0.9, "piece": 1}


def test_score_piece_raises_on_missing_probability():
    with patch.object(ns.fabryka_client, "decide", return_value={"answers": {}}):
        with pytest.raises(ns.fabryka_client.FabrykaUnexpectedResponse):
            ns.score_piece("tekst", _narratives(count=1))
