"""Tone and historical period of a WHOLE chapter: long chapters are split into fragments, not cut to the first 8 000
characters, and the per-fragment answers are merged (library/chapter_fragments.py, tones.py, time_periods.py).
"""

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("unidecode")

from library import chapter_fragments, time_periods, tones  # noqa: E402


def _tone(emotion="neutralny", sentiment="neutralne", intensity="niska", secondary=None, registers=None, evidence="e"):
    return {"emotion": emotion, "secondary_emotions": secondary, "sentiment": sentiment,
            "intensity": intensity, "registers": registers, "evidence": evidence}


def _period(label, start=None, end=None, confidence="medium", evidence="dowód"):
    return {"subject_period_label": label, "subject_period_start_year": start,
            "subject_period_end_year": end, "confidence": confidence, "evidence": evidence}


def _paragraphs(count: int, size: int) -> str:
    return "\n\n".join(f"{index:03d} " + "x" * (size - 4) for index in range(count))


# --- chapter_fragments ------------------------------------------------------------------------------------------


def test_short_chapter_is_one_fragment():
    fragments, skipped = chapter_fragments.chapter_fragments("krótki tekst", 8_000)

    assert fragments == ["krótki tekst"]
    assert skipped == 0


def test_empty_chapter_has_no_fragments_so_no_model_call():
    assert chapter_fragments.chapter_fragments("   \n\n  ", 8_000) == ([], 0)
    assert chapter_fragments.chapter_fragments(None, 8_000) == ([], 0)


def test_long_chapter_is_split_without_losing_a_paragraph():
    text = _paragraphs(40, 1_000)  # 40 000 characters

    fragments, skipped = chapter_fragments.chapter_fragments(text, 8_000)

    assert skipped == 0
    assert len(fragments) == 6
    assert all(len(fragment) <= 8_000 for fragment in fragments)
    assert "\n\n".join(fragments) == text


def test_fragment_cap_reports_what_it_left_out():
    text = _paragraphs(30, 1_000)  # two paragraphs plus the separator exceed 2 000, so one paragraph per fragment

    fragments, skipped = chapter_fragments.chapter_fragments(text, 2_000, max_fragments=5)

    assert len(fragments) == 5
    assert skipped == 25


def test_merge_reports_sums_counters_and_tolerates_reports_without_usage():
    merged = chapter_fragments.merge_fragment_reports(
        [{"invalid_json": 1, "rejected_invalid": 0}, {"invalid_json": 0, "rejected_invalid": 2}],
        counters=("invalid_json", "rejected_invalid"), fragments=2, skipped=3,
    )

    assert merged == {"invalid_json": 1, "rejected_invalid": 2, "fragments": 2, "fragments_skipped": 3}


def test_merge_reports_combines_usage_when_present():
    usage = {"llm_calls": 1, "usage_log_ids": [4], "llm_tokens": 10, "llm_cost_amount": "0.5",
             "llm_cost_currency": "PLN", "llm_cost_status": "estimated"}

    merged = chapter_fragments.merge_fragment_reports(
        [{**usage, "invalid_json": 0}, {**usage, "usage_log_ids": [5], "invalid_json": 0}],
        counters=("invalid_json",), fragments=2, skipped=0,
    )

    assert merged["llm_calls"] == 2
    assert merged["llm_tokens"] == 20
    assert merged["llm_cost_amount"] == "1.0"


# --- tones ------------------------------------------------------------------------------------------------------


def test_single_fragment_tone_is_returned_unchanged():
    tone = _tone("radosny", "pozytywne", "wysoka", secondary="smutny", registers="potoczny")

    assert tones.merge_tones([(tone, 500)]) is tone


def test_merged_tone_takes_the_emotion_covering_most_text():
    merged = tones.merge_tones([
        (_tone("radosny", "pozytywne", evidence="krótko"), 1_000),
        (_tone("gniewny", "negatywne", evidence="długo i gniewnie"), 6_000),
    ])

    assert merged["emotion"] == "gniewny"
    assert merged["evidence"] == "długo i gniewnie"
    assert merged["secondary_emotions"] == "radosny"


def test_merged_tone_keeps_a_dominant_sentiment_and_calls_the_rest_mixed():
    dominant = tones.merge_tones([
        (_tone("smutny", "negatywne"), 8_000),
        (_tone("neutralny", "neutralne"), 2_000),
    ])
    mixed = tones.merge_tones([
        (_tone("smutny", "negatywne"), 5_000),
        (_tone("radosny", "pozytywne"), 5_000),
    ])

    assert dominant["sentiment"] == "negatywne"
    assert mixed["sentiment"] == "mieszane"


def test_merged_tone_takes_the_highest_intensity_and_the_most_common_registers():
    merged = tones.merge_tones([
        (_tone(intensity="niska", registers="formalny"), 4_000),
        (_tone(intensity="wysoka", registers="potoczny, ironiczny"), 1_000),
        (_tone(intensity="średnia", registers="formalny"), 4_000),
    ])

    assert merged["intensity"] == "wysoka"
    assert merged["registers"] == "formalny, potoczny"  # two at most, the heavier first


def test_merged_secondary_emotions_never_repeat_the_main_one_and_stay_within_the_limit():
    merged = tones.merge_tones([
        (_tone("smutny", secondary="gniewny, radosny, refleksyjny"), 6_000),
        (_tone("smutny", secondary="smutny, alarmistyczny"), 6_000),
    ])

    assert merged["emotion"] == "smutny"
    assert "smutny" not in merged["secondary_emotions"].split(", ")
    assert len(merged["secondary_emotions"].split(", ")) <= tones.MAX_SECONDARY_EMOTIONS


def test_equal_weight_emotions_keep_the_earlier_fragment():
    merged = tones.merge_tones([(_tone("radosny", "pozytywne"), 100), (_tone("smutny", "negatywne"), 100)])

    assert merged["emotion"] == "radosny"


def test_long_chapter_tone_reads_every_fragment(monkeypatch):
    text = _paragraphs(40, 1_000)
    seen: list[str] = []

    def fake_classify(fragment, model, *, document_id=None):
        seen.append(fragment)
        return _tone("smutny", "negatywne"), {"invalid_json": 0, "rejected_invalid": 0}

    monkeypatch.setattr(tones, "classify_fragment", fake_classify)

    tone, report = tones.classify_chapter(text, "m")

    assert "\n\n".join(seen) == text, "the whole chapter must reach the model, not its first 8 000 characters"
    assert report["fragments"] == len(seen) == 6
    assert report["fragments_skipped"] == 0
    assert tone["emotion"] == "smutny"


def test_chapter_tone_ignores_failed_fragments_but_counts_them(monkeypatch):
    answers = iter([
        (None, {"invalid_json": 1, "rejected_invalid": 0}),
        (_tone("radosny", "pozytywne"), {"invalid_json": 0, "rejected_invalid": 0}),
    ])
    monkeypatch.setattr(tones, "classify_fragment", lambda *_a, **_k: next(answers))

    tone, report = tones.classify_chapter(_paragraphs(12, 1_000), "m")

    assert tone["emotion"] == "radosny"
    assert report["invalid_json"] == 1


def test_empty_chapter_makes_no_model_call(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the model must not be called for an empty chapter")

    monkeypatch.setattr(tones, "classify_fragment", boom)

    assert tones.classify_chapter("", "m")[0] is None


# --- time periods -----------------------------------------------------------------------------------------------


def test_single_fragment_periods_are_returned_unchanged():
    periods = [_period("zimna wojna", 1947, 1991)]

    assert time_periods.merge_periods([(periods, 500)]) is periods


def test_same_period_in_two_fragments_widens_its_years_and_keeps_the_best_confidence():
    merged = time_periods.merge_periods([
        ([_period("Zimna wojna", 1950, 1970, "low", "słabo")], 4_000),
        ([_period("zimna wojna", 1947, 1991, "high", "mocno")], 4_000),
    ])

    assert len(merged) == 1
    assert merged[0]["subject_period_label"] == "Zimna wojna"
    assert (merged[0]["subject_period_start_year"], merged[0]["subject_period_end_year"]) == (1947, 1991)
    assert (merged[0]["confidence"], merged[0]["evidence"]) == ("high", "mocno")


def test_main_period_is_the_one_covering_most_text_and_the_list_is_capped():
    merged = time_periods.merge_periods([
        ([_period("A")], 1_000),
        ([_period("B"), _period("C")], 6_000),
        ([_period("D")], 3_000),
    ])

    assert [period["subject_period_label"] for period in merged] == ["B", "C", "D"]
    assert len(merged) == time_periods.MAX_PERIODS_PER_CHAPTER


def test_merge_keeps_a_known_year_when_another_fragment_has_none():
    merged = time_periods.merge_periods([
        ([_period("średniowiecze", None, None)], 1_000),
        ([_period("średniowiecze", 476, 1492)], 1_000),
    ])

    assert (merged[0]["subject_period_start_year"], merged[0]["subject_period_end_year"]) == (476, 1492)


def test_long_chapter_periods_read_every_fragment(monkeypatch):
    text = _paragraphs(40, 1_000)
    seen: list[str] = []

    def fake_classify(fragment, model, *, document_id=None):
        seen.append(fragment)
        return [_period("II wojna światowa", 1939, 1945)], {"invalid_json": 0, "rejected_invalid": 0}

    monkeypatch.setattr(time_periods, "classify_fragment", fake_classify)

    periods, report = time_periods.classify_chapter(text, "m")

    assert "\n\n".join(seen) == text
    assert report["fragments"] == 6
    assert [period["subject_period_label"] for period in periods] == ["II wojna światowa"]


def test_empty_chapter_has_no_periods_and_no_model_call(monkeypatch):
    monkeypatch.setattr(time_periods, "classify_fragment", lambda *_a, **_k: pytest.fail("model called"))

    periods, report = time_periods.classify_chapter("", "m")

    assert periods == []
    assert report["fragments"] == 0


def test_refresh_keeps_previous_periods_when_the_only_answer_was_invalid(monkeypatch):
    from unittest.mock import MagicMock
    from types import SimpleNamespace

    session = MagicMock()
    monkeypatch.setattr(
        time_periods, "extract_document_periods",
        lambda *_a, **_k: {"model": "m", "periods": [], "chapters": [{"invalid_json": 1}]},
    )

    result = time_periods.refresh_document_periods(
        session, SimpleNamespace(id=1), chapter_position=2, keep_previous_on_failure=True,
    )

    assert result["kept_previous"] is True
    session.execute.assert_not_called()


def test_refresh_still_replaces_when_no_period_is_a_valid_answer(monkeypatch):
    from unittest.mock import MagicMock
    from types import SimpleNamespace

    session = MagicMock()
    monkeypatch.setattr(
        time_periods, "extract_document_periods",
        lambda *_a, **_k: {"model": "m", "periods": [], "chapters": [{"invalid_json": 0}]},
    )

    result = time_periods.refresh_document_periods(
        session, SimpleNamespace(id=1), chapter_position=2, keep_previous_on_failure=True,
    )

    assert "kept_previous" not in result
    session.execute.assert_called_once()
