"""Passages that stand out from a chapter's tone, or carry its substance (library/tone_spans.py)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("unidecode")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from library import tone_spans  # noqa: E402
from library.db.models import DocumentToneSpan  # noqa: E402

SPITE = "Ale oczywiście, nasz wielki ekspert znów wie lepiej od wszystkich, jak zwykle bez żadnych dowodów."
KEY = "Problem polega na tym, że umowa przewiduje karę umowną, której nikt nie jest w stanie wyegzekwować."
TEXT = f"Wstęp artykułu o umowie.\n\n{SPITE} {KEY} Dalej autor wraca do spokojnego tonu opisu sprawy."


def _answer(*items) -> SimpleNamespace:
    return SimpleNamespace(response_text=json.dumps(list(items), ensure_ascii=False), usage=None)


def _item(role="odstaje", label="złośliwy", quote=SPITE, **extra):
    return {"rola": role, "etykieta": label, "cytat": quote, "uzasadnienie": "powód", **extra}


# --- parsing ----------------------------------------------------------------------------------------------------


def test_fenced_json_is_parsed():
    spans, invalid = tone_spans.parse_spans_response("```json\n[{\"rola\": \"kluczowy\"}]\n```")

    assert spans == [{"rola": "kluczowy"}]
    assert invalid is False


def test_truncated_answer_recovers_the_complete_objects():
    raw = '[{"rola": "odstaje", "cytat": "a"}, {"rola": "kluczowy", "cytat": "dru'

    spans, invalid = tone_spans.parse_spans_response(raw)

    assert spans == [{"rola": "odstaje", "cytat": "a"}]
    assert invalid is True


def test_unusable_answer_is_reported_not_raised():
    assert tone_spans.parse_spans_response("nie JSON") == ([], True)


def test_a_wrapping_object_is_unwrapped():
    spans, _ = tone_spans.parse_spans_response('{"fragmenty": [{"rola": "odstaje"}]}')

    assert spans == [{"rola": "odstaje"}]


# --- the quote must be in the text -------------------------------------------------------------------------------


def test_exact_quote_is_returned_as_is():
    assert tone_spans.locate_quote(f"  {SPITE} ", TEXT) == SPITE


def test_a_quote_the_model_joined_over_a_line_break_is_restored_to_the_text_wording():
    text = "Pierwsza część zdania, która jest\ndość długa i kończy się tutaj."

    located = tone_spans.locate_quote("część zdania, która jest dość długa", text)

    assert located == "część zdania, która jest\ndość długa"


def test_an_invented_quote_is_refused():
    assert tone_spans.locate_quote("Tego zdania nigdy nie było w żadnym tekście.", TEXT) is None


def test_typography_differences_keep_the_quote_for_a_paragraph_tint():
    text = "Powiedział „to jest absurd” i wyszedł z sali bez słowa wyjaśnienia."

    assert tone_spans.locate_quote('Powiedział "to jest absurd" i wyszedł z sali', text) == (
        'Powiedział "to jest absurd" i wyszedł z sali'
    )


# --- validation of a candidate ----------------------------------------------------------------------------------


def test_outlier_label_comes_from_the_closed_list_even_without_diacritics():
    span, reason = tone_spans.normalize_span(_item(label="zlosliwy"), TEXT)

    assert reason is None
    assert (span["role"], span["label"], span["importance"]) == ("outlier", "złośliwy", None)


def test_unknown_outlier_label_is_invalid():
    assert tone_spans.normalize_span(_item(label="fajny"), TEXT) == (None, "invalid")


def test_unknown_role_is_invalid():
    assert tone_spans.normalize_span(_item(role="ważny"), TEXT) == (None, "invalid")


def test_quote_outside_the_length_limits_is_invalid():
    assert tone_spans.normalize_span(_item(quote="za krótki"), TEXT) == (None, "invalid")
    assert tone_spans.normalize_span(_item(quote="x" * 600), TEXT) == (None, "invalid")


def test_quote_missing_from_the_text_is_reported_separately():
    assert tone_spans.normalize_span(_item(quote="To zdanie jest całkowicie zmyślone przez model."), TEXT) == (
        None, "no_quote",
    )


def test_key_passage_gets_its_label_and_a_clamped_importance():
    span, _ = tone_spans.normalize_span(_item(role="kluczowy", label="cokolwiek", quote=KEY, waga=9), TEXT)
    default, _ = tone_spans.normalize_span(_item(role="kluczowy", quote=KEY, waga="?"), TEXT)

    assert (span["label"], span["importance"]) == ("kluczowy", 3)
    assert default["importance"] == 2


# --- one fragment -----------------------------------------------------------------------------------------------


def test_key_sentence_inside_a_malicious_remark_is_kept_as_its_own_passage(monkeypatch):
    remark = f"{SPITE} {KEY}"
    monkeypatch.setattr(
        tone_spans, "ai_ask",
        lambda *a, **k: _answer(_item(quote=remark), _item(role="kluczowy", label="kluczowy", quote=KEY, waga=3)),
    )

    spans, report = tone_spans.detect_in_fragment(TEXT, "m")

    assert [(s["role"], s["quote"]) for s in spans] == [("outlier", remark), ("key", KEY)]
    assert report["rejected_no_quote"] == 0


def test_invented_and_invalid_candidates_are_counted_and_dropped(monkeypatch):
    monkeypatch.setattr(
        tone_spans, "ai_ask",
        lambda *a, **k: _answer(
            _item(), _item(quote="Zdanie, którego w tekście nie ma, ale wygląda wiarygodnie."), _item(label="fajny"),
        ),
    )

    spans, report = tone_spans.detect_in_fragment(TEXT, "m")

    assert len(spans) == 1
    assert (report["rejected_no_quote"], report["rejected_invalid"]) == (1, 1)


def test_only_one_key_passage_per_fragment(monkeypatch):
    other = "Dalej autor wraca do spokojnego tonu opisu sprawy."
    monkeypatch.setattr(
        tone_spans, "ai_ask",
        lambda *a, **k: _answer(
            _item(role="kluczowy", quote=KEY, waga=3), _item(role="kluczowy", quote=other, waga=1),
        ),
    )

    spans, _ = tone_spans.detect_in_fragment(TEXT, "m")

    assert [s["quote"] for s in spans] == [KEY]


def test_unusable_answer_yields_no_passages_and_a_flag(monkeypatch):
    monkeypatch.setattr(tone_spans, "ai_ask", lambda *a, **k: SimpleNamespace(response_text="śmieci", usage=None))

    spans, report = tone_spans.detect_in_fragment(TEXT, "m")

    assert spans == []
    assert report["invalid_json"] == 1


# --- a chapter ---------------------------------------------------------------------------------------------------


def _span(role="outlier", quote="q" * 20, importance=None):
    return {"role": role, "label": "złośliwy" if role == "outlier" else "kluczowy", "quote": quote,
            "note": None, "importance": importance}


def test_repeated_passages_collapse_and_only_the_heaviest_keys_stay():
    keys = [_span("key", f"klucz numer {n} " + "x" * 10, importance=1 + n % 3) for n in range(8)]
    repeat = _span("outlier", "To samo  zdanie złośliwe")
    again = _span("outlier", "to samo zdanie  złośliwe")

    chosen = tone_spans.select_spans([repeat, *keys, again])

    assert sum(1 for s in chosen if s["role"] == "outlier") == 1
    kept = [s for s in chosen if s["role"] == "key"]
    assert len(kept) == tone_spans.MAX_KEY_PER_CHAPTER
    assert min(s["importance"] for s in kept) >= sorted((s["importance"] for s in keys), reverse=True)[4]


def test_detect_reads_every_fragment_of_a_long_chapter(monkeypatch):
    text = "\n\n".join(f"{n:03d} " + "x" * 996 for n in range(40))  # 40 000 characters
    seen = []

    def fake(fragment, model, *, document_id=None):
        seen.append(fragment)
        return [], {"invalid_json": 0, "rejected_no_quote": 0, "rejected_invalid": 0}

    monkeypatch.setattr(tone_spans, "detect_in_fragment", fake)

    result = tone_spans.detect_spans(SimpleNamespace(id=1, text_md=text, text=None, title="T"), "m")

    assert "\n\n".join(seen) == text
    assert result["chapters"][0]["fragments"] == len(seen) == 6


def test_detect_stores_the_chapter_position_of_each_passage(monkeypatch):
    doc = SimpleNamespace(id=1, text_md="## A\n\nTekst pierwszy.\n\n## B\n\nTekst drugi.", text=None, title="T")
    monkeypatch.setattr(
        tone_spans, "detect_in_fragment",
        lambda fragment, model, *, document_id=None: ([_span("outlier", fragment.strip()[:20])], {"invalid_json": 0}),
    )

    result = tone_spans.detect_spans(doc, "m")

    assert [s["chapter_position"] for s in result["spans"]] == [1, 2]


# --- storing: a reviewer's decision survives a re-detection -------------------------------------------------------


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    DocumentToneSpan.__table__.create(engine)
    with Session(engine) as sess:
        yield sess


def _store(session, quote, status="proposed", chapter=None, role="outlier"):
    row = DocumentToneSpan(document_id=1, chapter_position=chapter, role=role, label="złośliwy", quote=quote,
                           status=status)
    session.add(row)
    session.flush()
    return row


def _doc():
    return SimpleNamespace(id=1, text_md="Artykuł bez nagłówków.", text=None, title="T")


def test_redetection_replaces_proposals_but_keeps_what_was_settled(session, monkeypatch):
    confirmed = _store(session, "Zatwierdzone zdanie złośliwe.", "confirmed")
    rejected = _store(session, "Odrzucone zdanie złośliwe.", "rejected")
    _store(session, "Stara propozycja do zastąpienia.", "proposed")
    found = [_span("outlier", "Odrzucone  zdanie złośliwe."), _span("outlier", "Zupełnie nowe zdanie złośliwe."),
             _span("outlier", "Zatwierdzone zdanie złośliwe.")]
    monkeypatch.setattr(
        tone_spans, "detect_spans",
        lambda doc, model, chapter_position=None: {"model": model, "chapters": [], "spans": [
            {"chapter_position": None, **span} for span in found]},
    )

    result = tone_spans.refresh_document_tone_spans(session, _doc(), "m")
    session.flush()

    quotes = {row.quote: row.status for row in session.query(DocumentToneSpan).all()}
    assert quotes == {
        "Zatwierdzone zdanie złośliwe.": "confirmed",
        "Odrzucone zdanie złośliwe.": "rejected",
        "Zupełnie nowe zdanie złośliwe.": "proposed",
    }, "a rejected passage must not come back as a proposal, and old proposals must go"
    assert {row.id for row in result["all"]} >= {confirmed.id, rejected.id}
    assert len(result["all"]) == 3


def test_redetection_of_one_chapter_leaves_the_other_chapters_alone(session, monkeypatch):
    other = _store(session, "Propozycja z innego rozdziału.", "proposed", chapter=2)
    _store(session, "Propozycja z tego rozdziału.", "proposed", chapter=1)
    monkeypatch.setattr(
        tone_spans, "detect_spans",
        lambda doc, model, chapter_position=None: {"model": model, "chapters": [], "spans": []},
    )

    tone_spans.refresh_document_tone_spans(session, _doc(), "m", chapter_position=1)
    session.flush()

    assert [row.id for row in session.query(DocumentToneSpan).all()] == [other.id]


# --- the tone without the outliers -------------------------------------------------------------------------------


def _core_session(outliers, tone_row):
    results = [
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: outliers)),
        SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: tone_row)),
    ]
    sess = MagicMock()
    sess.execute.side_effect = results
    return sess


LONG = "Rzeczowy opis sprawy. " * 30


def test_core_tone_classifies_the_text_without_the_outliers(monkeypatch):
    doc = SimpleNamespace(id=1, text_md=f"{LONG}{SPITE} {LONG}", text=None, title="T")
    tone_row = SimpleNamespace(core_tone=None)
    outlier = SimpleNamespace(quote=SPITE)
    seen = {}

    def fake_classify(text, model, *, document_id=None):
        seen["text"] = text
        return {"emotion": "neutralny", "sentiment": "neutralne", "intensity": "niska"}, {"invalid_json": 0}

    monkeypatch.setattr(tone_spans, "classify_chapter", fake_classify)

    result = tone_spans.recompute_core_tone(_core_session([outlier], tone_row), doc, "m")

    assert SPITE not in seen["text"]
    assert tone_row.core_tone["emotion"] == "neutralny"
    assert tone_row.core_tone["excluded"] == 1
    assert result["core_tone"] is tone_row.core_tone


@pytest.mark.parametrize(("outliers", "tone_row", "text", "code"), [
    ([], SimpleNamespace(core_tone=None), LONG, "no_outliers"),
    ([SimpleNamespace(quote=SPITE)], None, f"{LONG}{SPITE}", "no_tone"),
    ([SimpleNamespace(quote="Tego fragmentu nie ma w tekście wcale.")], SimpleNamespace(core_tone=None), LONG,
     "no_outliers"),
    ([SimpleNamespace(quote=SPITE)], SimpleNamespace(core_tone=None), f"Krótko. {SPITE}", "text_too_short"),
])
def test_core_tone_reports_why_it_cannot_be_computed(outliers, tone_row, text, code):
    doc = SimpleNamespace(id=1, text_md=text, text=None, title="T")

    with pytest.raises(ValueError, match=code):
        tone_spans.recompute_core_tone(_core_session(outliers, tone_row), doc, "m")


def test_core_tone_fails_when_the_model_gives_nothing_usable(monkeypatch):
    doc = SimpleNamespace(id=1, text_md=f"{LONG}{SPITE} {LONG}", text=None, title="T")
    monkeypatch.setattr(tone_spans, "classify_chapter", lambda *a, **k: (None, {}))

    with pytest.raises(ValueError, match="failed"):
        tone_spans.recompute_core_tone(
            _core_session([SimpleNamespace(quote=SPITE)], SimpleNamespace(core_tone=None)), doc, "m",
        )
