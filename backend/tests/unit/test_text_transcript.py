import json

from library import text_transcript


def test_split_text_and_time_none():
    result = text_transcript.split_text_and_time(None)
    assert result == {}


def test_split_text_and_time_empty():
    result = text_transcript.split_text_and_time('')
    assert result == {}


def test_split_text_and_time_no_match():
    result = text_transcript.split_text_and_time('random string')
    assert result == {}


def test_split_text_and_time_single_match():
    result = text_transcript.split_text_and_time('text 12:30')
    assert result == {'text': 'text', 'czas': '12:30'}


def test_split_text_and_time_single_match_2():
    result = text_transcript.split_text_and_time('12:30 - text')
    assert result == {'text': 'text', 'czas': '12:30'}


def test_split_text_and_time_single_match_3():
    result = text_transcript.split_text_and_time('12:30:00 - text')
    assert result == {'text': 'text', 'czas': '12:30:00'}


def test_youtube_split_chapters_from_zero():
    chapters = "0:00 Start\n01:00 Dalej"
    entries = [
        {"text": "a", "start": 0.0},
        {"text": "b", "start": 10.0},
        {"text": "c", "start": 70.0},
    ]
    result = text_transcript.youtube_titles_split_with_chapters(json.dumps(entries), chapters)
    assert result.startswith("Start\na b")
    assert "\n\nDalej\nc" in result


def test_youtube_split_intro_before_first_chapter():
    """Regression: chapters auto-parsed from description often start after 0:00.

    Entries before the first chapter used to blindly advance the chapter index
    on every segment, ending in IndexError (doc 9188, CAPTIONS_FETCH_ERROR).
    """
    chapters = "01:07 Pierwszy\n05:20 Drugi"
    entries = [
        {"text": "intro jeden", "start": 0.0},
        {"text": "intro dwa", "start": 30.0},
        {"text": "intro trzy", "start": 60.0},
        {"text": "tresc pierwszego", "start": 68.0},
        {"text": "tresc drugiego", "start": 321.0},
    ]
    result = text_transcript.youtube_titles_split_with_chapters(json.dumps(entries), chapters)
    assert result.startswith("intro jeden intro dwa intro trzy")
    assert "\n\nPierwszy\ntresc pierwszego" in result
    assert "\n\nDrugi\ntresc drugiego" in result


def test_youtube_split_empty_chapter_keeps_all_headers():
    chapters = "0:00 A\n01:00 B\n02:00 C"
    entries = [
        {"text": "x", "start": 0.0},
        {"text": "y", "start": 130.0},  # jumps straight to chapter C
    ]
    result = text_transcript.youtube_titles_split_with_chapters(json.dumps(entries), chapters)
    assert "A\nx" in result
    assert "B" in result
    assert "C\ny" in result


def test_youtube_split_out_of_order_entry_does_not_reopen_chapter():
    chapters = "0:00 A\n01:00 B"
    entries = [
        {"text": "x", "start": 0.0},
        {"text": "y", "start": 70.0},
        {"text": "z", "start": 65.0},  # slightly out of order — stays in B
    ]
    result = text_transcript.youtube_titles_split_with_chapters(json.dumps(entries), chapters)
    assert "B\ny z" in result
    assert result.count("B") == 1


def test_text_split_with_chapters_intro_before_first_chapter():
    """Same regression for the AWS Transcribe variant."""
    chapters = "01:00 Pierwszy"
    transcript = {
        "results": {
            "items": [
                {"start_time": "0.0", "alternatives": [{"content": "intro"}]},
                {"start_time": "30.0", "alternatives": [{"content": "dalej"}]},
                {"alternatives": [{"content": "."}]},
                {"start_time": "65.0", "alternatives": [{"content": "tresc"}]},
            ]
        }
    }
    result = text_transcript.text_split_with_chapters(json.dumps(transcript), chapters)
    assert result.startswith("intro dalej.")
    assert "\n\nPierwszy\ntresc" in result
